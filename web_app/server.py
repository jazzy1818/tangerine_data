"""Same-origin local website and API. Run with python -m uvicorn web_app.server:app."""
from contextlib import asynccontextmanager
from pathlib import Path
import re
import secrets
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import engine
from plan_classification.config import classifier_settings
from plan_classification.schemas import MODULES, MODULE_DESCRIPTIONS, ShockScenario
from . import analytics, portfolio, scenario_intake, service, store
from .contracts import RunInput, ScenarioInput, ReviewUpdate

STATIC = Path(__file__).with_name('static')
COOKIE = 'tangerine_workspace'


@asynccontextmanager
async def lifespan(app):
    store.interrupted()
    yield


app = FastAPI(title='Tangerine Resilience API', version='1.0.0', lifespan=lifespan,
              docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)


@app.middleware('http')
async def local_workspace(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if origin and urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Cross-origin changes are not accepted.'}, status_code=403)
        if request.url.path.startswith('/api/') and not request.headers.get('content-type', '').startswith('application/json'):
            return JSONResponse({'detail': 'Use application/json.'}, status_code=415)
    session = request.cookies.get(COOKIE, '')
    fresh = not re.fullmatch(r'[a-f0-9]{64}', session)
    request.state.session_id = secrets.token_hex(32) if fresh else session
    response = await call_next(request)
    if fresh:
        response.set_cookie(COOKIE, request.state.session_id, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', max_age=60*60*24*30)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    errors = [{'field': '.'.join(str(p) for p in e['loc'] if p != 'body'), 'message': e['msg']}
              for e in exc.errors()]
    return JSONResponse({'detail': 'Check the amounts, dates and required information.', 'errors': errors}, status_code=422)


@app.exception_handler(ValueError)
async def invalid_value(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=422)


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/config')
def config():
    error = None
    try:
        settings = classifier_settings()
    except ValueError as exc:
        settings, error = {}, str(exc)
    return {'modules': MODULES, 'module_descriptions': MODULE_DESCRIPTIONS,
            'default_backend': 'jev' if settings.get('OPENROUTER_API_KEY') else 'gemini' if settings.get('GEMINI_API_KEY') else 'rules',
            'providers': {'rules': {'configured': True, 'label': 'Local baseline'},
                          'jev': {'configured': bool(settings.get('OPENROUTER_API_KEY')), 'label': 'Jev / OpenRouter'},
                          'gemini': {'configured': bool(settings.get('GEMINI_API_KEY')), 'label': 'Gemini'}},
            'scenario_intake': {'configured': bool(settings.get('GEMINI_API_KEY'))},
            'configuration_error': error, 'scenario_schema': ShockScenario.model_json_schema()}


@app.get('/api/accounts')
def accounts(q: str = Query(default='', max_length=20),
             filter: Literal['all', 'arrears', 'surplus', 'shortfall', 'no_loan'] = 'all',
             offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100)):
    return analytics.accounts(q, filter, offset, limit)


@app.get('/api/customers/{account_id}')
def customer(account_id: int):
    if account_id not in engine.get_account_ids():
        raise HTTPException(404, 'This account is not in the supplied dataset.')
    return service.customer_view(engine.know_customer(account_id))


@app.get('/api/discovery')
def discovery(cohort: Literal['recurring_shortfalls', 'thin_reserves', 'payment_timing', 'shock_exposure'] = 'recurring_shortfalls',
              offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
              refresh: bool = False):
    return portfolio.discovery(cohort, offset, limit, refresh)


@app.post('/api/scenarios/preview')
def preview(request: ScenarioInput):
    return service.preview(request)


@app.post('/api/scenarios/interpret')
def interpret_scenario(payload: scenario_intake.IntakeRequest, request: Request):
    if payload.account_id not in engine.get_account_ids():
        raise HTTPException(404, 'This account is not in the supplied dataset.')
    try:
        return scenario_intake.interpret(payload, request.state.session_id)
    except scenario_intake.IntakeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post('/api/runs', status_code=202)
def create_run(payload: RunInput, request: Request, tasks: BackgroundTasks):
    # Stateless preflight validates the account, structured case and dated cash path.
    service.preview(payload)
    try:
        created = store.reserve(request.state.session_id, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        tasks.add_task(service.execute_run, request.state.session_id, payload)
    return {'id': str(payload.request_id), 'created': created}


@app.get('/api/runs')
def runs(request: Request):
    return {'items': store.list_runs(request.state.session_id)}


@app.get('/api/runs/{run_id}')
def run(run_id: UUID, request: Request):
    result = store.get(request.state.session_id, str(run_id))
    if result is None:
        raise HTTPException(404, 'This analysis is not in this browser workspace.')
    return result


@app.patch('/api/runs/{run_id}/review')
def update_review(run_id: UUID, payload: ReviewUpdate, request: Request):
    try:
        return store.update_review(request.state.session_id, str(run_id), payload)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


app.mount('/assets', StaticFiles(directory=STATIC), name='assets')


@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html', headers={'Cache-Control': 'no-cache'})

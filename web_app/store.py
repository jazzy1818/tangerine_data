"""Immutable, session-scoped analysis records. Never stores API credentials."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parents[1] / 'logs' / 'website.sqlite3'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def connection():
    DB_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(DB_PATH, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(DB_PATH, timeout=15) as db:
        db.row_factory = sqlite3.Row
        db.execute('''CREATE TABLE IF NOT EXISTS runs (
            id TEXT NOT NULL, session_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT, error TEXT,
            PRIMARY KEY (session_id, id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS case_reviews (
            session_id TEXT NOT NULL, run_id TEXT NOT NULL, version INTEGER NOT NULL,
            updated_at TEXT NOT NULL, details TEXT NOT NULL,
            PRIMARY KEY (session_id, run_id))''')
        yield db


def reserve(session_id, request):
    payload = request.model_dump(mode='json')
    serialized = json.dumps(payload, sort_keys=True, allow_nan=False)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    run_id = str(request.request_id)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT fingerprint FROM runs WHERE session_id=? AND id=?',
                              (session_id, run_id)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise ValueError('This request ID belongs to a different scenario. Start a new analysis.')
            return False
        db.execute('INSERT INTO runs (id,session_id,fingerprint,created_at,status,request) VALUES (?,?,?,?,?,?)',
                   (run_id, session_id, fingerprint, now(), 'running', serialized))
    return True


def finish(session_id, run_id, *, result=None, error=None):
    serialized = json.dumps(result, allow_nan=False) if result is not None else None
    with connection() as db:
        db.execute('UPDATE runs SET status=?,finished_at=?,result=?,error=? WHERE session_id=? AND id=?',
                   ('failed' if error else 'complete', now(), serialized, error, session_id, run_id))


def interrupted():
    """Single-process server startup: an interrupted run is never silently retried/billed."""
    with connection() as db:
        db.execute("UPDATE runs SET status='failed',finished_at=?,error=? WHERE status='running'",
                   (now(), 'The server stopped before this analysis finished. Review the request log before starting another API run.'))


def get(session_id, run_id):
    with connection() as db:
        row = db.execute('SELECT * FROM runs WHERE session_id=? AND id=?', (session_id, run_id)).fetchone()
        review = db.execute('SELECT details FROM case_reviews WHERE session_id=? AND run_id=?', (session_id, run_id)).fetchone()
    if row is None:
        return None
    return {'id': row['id'], 'created_at': row['created_at'], 'finished_at': row['finished_at'],
            'status': row['status'], 'request': json.loads(row['request']),
            'result': json.loads(row['result']) if row['result'] else None, 'error': row['error'],
            'review': json.loads(review['details']) if review else default_review(json.loads(row['request']))}


def default_review(request):
    return {'version': 0, 'status': 'in_progress', 'owner': request.get('review_details', {}).get('prepared_by', ''),
            'follow_up_date': None, 'notes': '', 'completed_items': [], 'updated_at': None}


def update_review(session_id, run_id, update):
    """Staff notes never change the immutable financial assessment or call a model."""
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = db.execute('SELECT status FROM runs WHERE session_id=? AND id=?', (session_id, run_id)).fetchone()
        if run is None:
            raise LookupError('This review could not be found in your workspace.')
        if run['status'] != 'complete':
            raise ValueError('Wait for the assessment to finish before recording the review outcome.')
        previous = db.execute('SELECT version FROM case_reviews WHERE session_id=? AND run_id=?',
                              (session_id, run_id)).fetchone()
        version = previous['version'] if previous else 0
        if version != update.version:
            raise ValueError('This review changed in another window. Reopen it before saving your notes.')
        details = {**update.model_dump(mode='json'), 'version': version + 1, 'updated_at': now()}
        db.execute('INSERT INTO case_reviews (session_id,run_id,version,updated_at,details) VALUES (?,?,?,?,?) '
                   'ON CONFLICT(session_id,run_id) DO UPDATE SET version=excluded.version,updated_at=excluded.updated_at,details=excluded.details',
                   (session_id, run_id, details['version'], details['updated_at'], json.dumps(details, allow_nan=False)))
        return details


def list_runs(session_id, limit=100):
    with connection() as db:
        rows = db.execute('SELECT id,created_at,finished_at,status,request,result,error FROM runs '
                          'WHERE session_id=? ORDER BY created_at DESC,rowid DESC LIMIT ?',
                          (session_id, limit)).fetchall()
        reviews = {r['run_id']: json.loads(r['details']) for r in db.execute(
            'SELECT run_id,details FROM case_reviews WHERE session_id=?', (session_id,)).fetchall()}
    records = []
    for row in rows:
        request = json.loads(row['request'])
        result = json.loads(row['result']) if row['result'] else {}
        classifier = result.get('classification', {})
        crisis = result.get('plans', {}).get('crisis_plan', {})
        path = crisis.get('no_action') or {}
        applied = crisis.get('applied_plan') or {}
        records.append({'id': row['id'], 'created_at': row['created_at'], 'status': row['status'],
                        'title': request['title'], 'account_id': request['account_id'],
                        'requested_backend': request['backend'], 'actual_backend': classifier.get('actual_backend'),
                        'proposed_module': classifier.get('selection', {}).get('lead_module'),
                        'applied_module': crisis.get('lead_module'), 'api_calls': classifier.get('api_calls'),
                        'fallback_reason': classifier.get('fallback_reason'),
                        'funding_result_complete': applied.get('funding_result_complete', path.get('funding_result_complete')),
                        'remaining_cash_needed': applied.get('additional_cash_needed'),
                        'additional_cash_needed': path.get('additional_cash_needed'),
                        'ending_cash': path.get('ending_cash'), 'error': row['error']})
        records[-1]['review'] = reviews.get(row['id'], default_review(request))
        records[-1]['review_details'] = request.get('review_details', {})
    return records

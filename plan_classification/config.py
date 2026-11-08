"""Read approved provider settings without changing the process environment."""
import os
from pathlib import Path
import shlex


ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
SETTING_NAMES = ('OPENROUTER_API_KEY', 'JEV_MODEL', 'GEMINI_API_KEY', 'GEMINI_CLASSIFIER_MODEL',
                 'GEMINI_EXPLANATION_MODEL', 'GEMINI_ADVISOR_MODEL', 'GEMINI_SCENARIO_MODEL')


def classifier_settings():
    """Project .env values override inherited shell values; never execute the file."""
    settings = {name: os.environ[name] for name in SETTING_NAMES if name in os.environ}
    try:
        lines = ENV_FILE.read_text(encoding='utf-8-sig').splitlines()
    except FileNotFoundError:
        return settings
    except (OSError, UnicodeError):
        raise ValueError('Cannot read the project .env file.') from None
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, separator, raw = line.partition('=')
        name = name.strip()
        if not separator or name not in SETTING_NAMES:
            continue
        try:
            values = shlex.split(raw, comments=True, posix=True)
            if len(values) > 1:
                raise ValueError
        except ValueError:
            raise ValueError(f'Check the format of {name} in .env at line {number}.') from None
        settings[name] = values[0] if values else ''
    return settings


PROVIDER_ROUTES = {
    'jev': ('OPENROUTER_API_KEY', 'JEV_MODEL', 'typesafe/jev-1.14'),
    'gemini': ('GEMINI_API_KEY', 'GEMINI_CLASSIFIER_MODEL', 'gemini-3.5-flash-lite'),
    'explanation': ('GEMINI_API_KEY', 'GEMINI_EXPLANATION_MODEL', 'gemini-2.5-flash'),
    'daily': ('GEMINI_API_KEY', 'GEMINI_ADVISOR_MODEL', 'gemini-2.5-flash'),
    'scenario': ('GEMINI_API_KEY', 'GEMINI_SCENARIO_MODEL', 'gemini-3.5-flash-lite'),
}


def resolve_provider(route, *, api_key=None, model=None):
    """Explicit nonblank arguments > project file > shell. No environment mutation."""
    import re
    key_name,model_name,default=PROVIDER_ROUTES[route]
    if api_key is not None:
        if not isinstance(api_key,str):raise ValueError('Invalid provider settings.')
        api_key=api_key.strip()
    settings=classifier_settings()
    key=api_key or settings.get(key_name) or ''
    resolved=model or settings.get(model_name) or default
    if not isinstance(key,str) or not isinstance(resolved,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,199}',resolved):
        raise ValueError('Invalid provider settings.')
    return key.strip(),resolved


def provider_identity(route, *, api_key=None):
    """Public model identity only; credentials never enter cache keys or logs."""
    try:
        key,model=resolve_provider(route,api_key=api_key)
        return route,model,bool(key)
    except ValueError:
        return route,'configuration_unavailable'

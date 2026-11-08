"""Read classifier settings without exporting keys to other app components."""
import os
from pathlib import Path
import shlex


ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
SETTING_NAMES = ('OPENROUTER_API_KEY', 'JEV_MODEL', 'GEMINI_API_KEY', 'GEMINI_CLASSIFIER_MODEL')


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

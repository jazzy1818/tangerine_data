"""Local request metadata, excluding credentials and customer input/output text."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4


LOG_PATH = Path(__file__).resolve().parents[1] / 'logs' / 'classification.jsonl'
LOG_FIELDS = (
    'requested_backend', 'actual_backend', 'model_version', 'fallback_used',
    'fallback_reason', 'api_calls', 'invalid_outputs', 'elapsed_ms', 'input_hash',
    'input_tokens', 'output_tokens', 'thought_tokens', 'total_tokens', 'usage_complete',
    'cost_usd', 'implementation_version', 'prompt_version',
)


def request_record(result):
    data = result.model_dump(mode='json')
    return {
        'request_id': uuid4().hex,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'status': 'fallback' if result.fallback_used else
                  'api_success' if result.api_calls else 'local',
        **{name: data[name] for name in LOG_FIELDS},
        'lead_module': result.selection.lead_module,
        'support_modules': list(result.selection.support_modules),
    }


def append_request(record):
    """Append one JSON line; the UI keeps its session copy if disk writing fails."""
    LOG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, allow_nan=False) + '\n')

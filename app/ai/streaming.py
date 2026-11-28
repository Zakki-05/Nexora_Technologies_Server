import json
from typing import Any


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event frame with JSON payload."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

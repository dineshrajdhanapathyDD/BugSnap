"""Shared helpers for BugSnap Lambda functions."""
import json
import logging
import os
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

SEVERITIES = ["low", "medium", "high", "critical"]
STATUSES = ["open", "in_progress", "resolved", "closed"]
PRIORITY_BY_SEVERITY = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}
HIGH_PRIORITIES = ["P1", "P2"]


class _Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        return super().default(o)


def response(status_code, body):
    """API Gateway Lambda-proxy response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
        },
        "body": json.dumps(body, cls=_Encoder),
    }


def error(status_code, code, message, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return response(status_code, body)


def parse_body(event):
    """Return (dict, None) or (None, error_response)."""
    raw = event.get("body")
    if not raw:
        return None, error(400, "INVALID_REQUEST", "Request body is required")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None, error(400, "INVALID_JSON", "Request body must be valid JSON")
    if not isinstance(data, dict):
        return None, error(400, "INVALID_JSON", "Request body must be a JSON object")
    return data, None

"""GetBugs - GET /bugs?severity=&status=.

Reads through DynamoDB GSIs (no table Scan):
  status-created_at-index   (status, created_at)
  severity-created_at-index (severity, created_at)
Returns up to MAX_ITEMS newest bugs plus summary stats computed with COUNT queries.
"""
import os

import boto3
from boto3.dynamodb.conditions import Attr, Key

from common import HIGH_PRIORITIES, SEVERITIES, STATUSES, error, logger, response

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
STATUS_INDEX = "status-created_at-index"
SEVERITY_INDEX = "severity-created_at-index"
MAX_ITEMS = 200


def _query(index, attr, value, flt=None, limit=MAX_ITEMS):
    """Newest-first items for one partition key, following pagination up to `limit`."""
    kwargs = {
        "IndexName": index,
        "KeyConditionExpression": Key(attr).eq(value),
        "ScanIndexForward": False,
    }
    if flt is not None:
        kwargs["FilterExpression"] = flt
    items = []
    while len(items) < limit:
        res = table.query(**kwargs)
        items.extend(res.get("Items", []))
        if "LastEvaluatedKey" not in res:
            break
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]
    return items[:limit]


def _count(index, attr, value, flt=None):
    kwargs = {
        "IndexName": index,
        "KeyConditionExpression": Key(attr).eq(value),
        "Select": "COUNT",
    }
    if flt is not None:
        kwargs["FilterExpression"] = flt
    total = 0
    while True:
        res = table.query(**kwargs)
        total += res["Count"]
        if "LastEvaluatedKey" not in res:
            return total
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def _stats():
    by_status = {s: _count(STATUS_INDEX, "status", s) for s in STATUSES}
    high = sum(
        _count(STATUS_INDEX, "status", s, Attr("priority").is_in(HIGH_PRIORITIES))
        for s in ("open", "in_progress")
    )
    return {
        "total": sum(by_status.values()),
        "open": by_status["open"],
        "resolved": by_status["resolved"],
        "high_priority": high,
        "by_status": by_status,
    }


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    severity = (params.get("severity") or "").lower()
    status = (params.get("status") or "").lower()

    if severity and severity not in SEVERITIES:
        return error(400, "INVALID_FILTER", f"severity must be one of: {', '.join(SEVERITIES)}")
    if status and status not in STATUSES:
        return error(400, "INVALID_FILTER", f"status must be one of: {', '.join(STATUSES)}")

    try:
        if status:
            flt = Attr("severity").eq(severity) if severity else None
            items = _query(STATUS_INDEX, "status", status, flt)
        elif severity:
            items = _query(SEVERITY_INDEX, "severity", severity)
        else:
            items = []
            for s in STATUSES:
                items.extend(_query(STATUS_INDEX, "status", s))
            items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
            items = items[:MAX_ITEMS]
        stats = _stats()
    except Exception:
        logger.exception("Query failed")
        return error(500, "INTERNAL_ERROR", "Could not retrieve bugs")

    return response(200, {
        "bugs": items,
        "count": len(items),
        "truncated": len(items) >= MAX_ITEMS,
        "stats": stats,
    })

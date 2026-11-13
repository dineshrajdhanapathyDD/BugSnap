"""UpdateBug - PATCH /bugs/{id}. Updates the bug status."""
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from common import STATUSES, error, logger, parse_body, response

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def handler(event, context):
    bug_id = (event.get("pathParameters") or {}).get("id")
    if not bug_id:
        return error(400, "INVALID_REQUEST", "Bug id is required")

    data, err = parse_body(event)
    if err:
        return err

    status = data.get("status")
    if not isinstance(status, str) or status.strip().lower() not in STATUSES:
        return error(400, "VALIDATION_FAILED", f"status must be one of: {', '.join(STATUSES)}")
    status = status.strip().lower()

    try:
        res = table.update_item(
            Key={"bug_id": bug_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ConditionExpression="attribute_exists(bug_id)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status, ":u": datetime.now(timezone.utc).isoformat()},
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return error(404, "NOT_FOUND", f"Bug {bug_id} not found")
        logger.exception("UpdateItem failed")
        return error(500, "INTERNAL_ERROR", "Could not update bug")

    return response(200, res["Attributes"])

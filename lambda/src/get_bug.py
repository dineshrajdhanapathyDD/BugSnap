"""GetBug - GET /bugs/{id}. Includes a short-lived screenshot URL if attached."""
import os

import boto3

from common import error, logger, response

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
s3 = boto3.client("s3")
BUCKET = os.environ["ATTACHMENT_BUCKET"]


def handler(event, context):
    bug_id = (event.get("pathParameters") or {}).get("id")
    if not bug_id:
        return error(400, "INVALID_REQUEST", "Bug id is required")

    try:
        item = table.get_item(Key={"bug_id": bug_id}).get("Item")
    except Exception:
        logger.exception("GetItem failed")
        return error(500, "INTERNAL_ERROR", "Could not retrieve bug")

    if not item:
        return error(404, "NOT_FOUND", f"Bug {bug_id} not found")

    if item.get("attachment_key"):
        item["attachment_url"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": item["attachment_key"]},
            ExpiresIn=300,
        )
    return response(200, item)

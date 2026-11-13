"""SaveBug - Step Functions task. Stores the bug in DynamoDB."""
import os
from datetime import datetime, timezone

import boto3

from common import logger

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def handler(event, context):
    bug = event["bug"]
    now = datetime.now(timezone.utc).isoformat()
    item = {
        **bug,
        "priority": "UNASSIGNED",
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=item, ConditionExpression="attribute_not_exists(bug_id)")
    logger.info("Saved bug %s", item["bug_id"])
    return {"bug": item}

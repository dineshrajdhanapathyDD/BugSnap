"""PrioritizeBug - Step Functions task. Assigns priority from severity."""
import os
from datetime import datetime, timezone

import boto3

from common import PRIORITY_BY_SEVERITY, logger

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def handler(event, context):
    bug = event["bug"]
    priority = PRIORITY_BY_SEVERITY.get(bug["severity"], "P3")
    now = datetime.now(timezone.utc).isoformat()
    table.update_item(
        Key={"bug_id": bug["bug_id"]},
        UpdateExpression="SET priority = :p, updated_at = :u",
        ConditionExpression="attribute_exists(bug_id)",
        ExpressionAttributeValues={":p": priority, ":u": now},
    )
    logger.info("Bug %s prioritized as %s", bug["bug_id"], priority)
    return {"bug_id": bug["bug_id"], "priority": priority, "severity": bug["severity"]}

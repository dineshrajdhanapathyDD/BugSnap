"""CreateBug - POST /bugs. Starts the Step Functions workflow (synchronously)."""
import json
import os
import time

import boto3

from common import error, logger, parse_body, response

sfn = boto3.client("stepfunctions")
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]


def handler(event, context):
    data, err = parse_body(event)
    if err:
        return err

    payload = {
        "title": data.get("title"),
        "description": data.get("description"),
        "severity": data.get("severity"),
        "attachment_key": data.get("attachment_key"),
    }

    started = time.time()
    try:
        result = sfn.start_sync_execution(
            stateMachineArn=STATE_MACHINE_ARN, input=json.dumps(payload)
        )
    except Exception:
        logger.exception("Failed to start workflow")
        return error(500, "WORKFLOW_START_FAILED", "Could not start the bug workflow")

    duration_ms = int((time.time() - started) * 1000)
    workflow = {
        "execution_arn": result["executionArn"],
        "execution_name": result["name"],
        "status": result["status"],
        "duration_ms": duration_ms,
    }

    if result["status"] == "SUCCEEDED":
        out = json.loads(result["output"])
        return response(201, {**out, "workflow": workflow})

    if result["status"] == "FAILED" and result.get("error") == "ValidationFailed":
        try:
            details = json.loads(result.get("cause", "[]"))
        except ValueError:
            details = [result.get("cause", "Validation failed")]
        workflow["status"] = "FAILED"
        resp = error(400, "VALIDATION_FAILED", "Bug report failed validation", details)
        body = json.loads(resp["body"])
        body["workflow"] = workflow
        resp["body"] = json.dumps(body)
        return resp

    logger.error("Workflow ended with %s: %s %s", result["status"], result.get("error"), result.get("cause"))
    resp = error(500, "WORKFLOW_FAILED", "Bug workflow did not complete", [result.get("error", result["status"])])
    body = json.loads(resp["body"])
    body["workflow"] = workflow
    resp["body"] = json.dumps(body)
    return resp

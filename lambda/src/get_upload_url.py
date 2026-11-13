"""GetUploadUrl - POST /uploads. Returns a presigned PUT URL for a private screenshot."""
import os
import uuid

import boto3

from common import error, parse_body, response

s3 = boto3.client("s3")
BUCKET = os.environ["ATTACHMENT_BUCKET"]
TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}


def handler(event, context):
    data, err = parse_body(event)
    if err:
        return err
    content_type = data.get("content_type")
    if content_type not in TYPES:
        return error(400, "VALIDATION_FAILED", f"content_type must be one of: {', '.join(TYPES)}")

    key = f"screenshots/{uuid.uuid4()}.{TYPES[content_type]}"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )
    return response(200, {"upload_url": url, "attachment_key": key, "content_type": content_type})

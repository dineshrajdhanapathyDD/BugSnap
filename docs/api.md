# BugSnap API

Base URL: the `ApiUrl` stack output, for example `https://q8iwty3z1b.execute-api.us-east-1.amazonaws.com/prod`.
All bodies are JSON. CORS allows the website origin only.

Values: `severity` = `low | medium | high | critical`; `status` = `open | in_progress | resolved | closed`.
Priority is assigned by the workflow: critical = P1, high = P2, medium = P3, low = P4.

## Error format

```json
{ "error": { "code": "VALIDATION_FAILED", "message": "...", "details": ["..."] } }
```

Codes: `INVALID_REQUEST`, `INVALID_JSON`, `VALIDATION_FAILED`, `INVALID_FILTER`, `NOT_FOUND`, `WORKFLOW_START_FAILED`, `WORKFLOW_FAILED`, `INTERNAL_ERROR`.

## POST /bugs

Starts the Step Functions workflow (ValidateBug -> SaveBug -> PrioritizeBug) and waits for it.

Request:

```json
{ "title": "Login button broken", "description": "Nothing happens on click", "severity": "high", "attachment_key": "screenshots/<uuid>.png" }
```

`attachment_key` is optional (from `POST /uploads`).

201 response:

```json
{
  "bug_id": "uuid", "priority": "P2", "severity": "high", "workflow_status": "COMPLETED",
  "workflow": { "execution_arn": "...", "execution_name": "...", "status": "SUCCEEDED", "duration_ms": 412 }
}
```

400 response (validation failed inside the workflow):

```json
{
  "error": { "code": "VALIDATION_FAILED", "message": "Bug report failed validation", "details": ["title is required"] },
  "workflow": { "status": "FAILED", "execution_name": "...", "duration_ms": 120 }
}
```

## GET /bugs

Query parameters (optional): `severity`, `status`.

200 response:

```json
{
  "bugs": [ { "bug_id": "...", "title": "...", "description": "...", "severity": "high", "priority": "P2",
              "status": "open", "created_at": "ISO-8601", "updated_at": "ISO-8601" } ],
  "count": 1,
  "truncated": false,
  "stats": { "total": 10, "open": 6, "resolved": 3, "high_priority": 4,
             "by_status": { "open": 6, "in_progress": 1, "resolved": 3, "closed": 0 } }
}
```

At most 200 bugs are returned, newest first (`truncated` is true when that limit is hit). The list is read from DynamoDB global secondary indexes, not a table Scan. `stats` always covers all bugs, regardless of filters. `high_priority` counts P1/P2 bugs that are not resolved or closed.

## GET /bugs/{id}

200: the bug item. If it has an attachment, `attachment_url` is a presigned URL valid for 5 minutes. 404 `NOT_FOUND` if unknown.

## PATCH /bugs/{id}

Request: `{ "status": "resolved" }`. 200: the updated bug. 400 for an invalid status, 404 if unknown.

## POST /uploads

Request: `{ "content_type": "image/png" }` (png, jpeg, gif, webp).

200:

```json
{ "upload_url": "https://...presigned PUT...", "attachment_key": "screenshots/<uuid>.png", "content_type": "image/png" }
```

Upload with `PUT <upload_url>` and header `Content-Type` equal to the declared type. The URL expires after 5 minutes.

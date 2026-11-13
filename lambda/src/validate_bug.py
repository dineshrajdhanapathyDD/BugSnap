"""ValidateBug - Step Functions task. Validates input and assigns a bug_id."""
import uuid

from common import SEVERITIES, logger

MAX_TITLE = 120
MAX_DESCRIPTION = 5000


def handler(event, context):
    errors = []
    title = event.get("title")
    description = event.get("description")
    severity = event.get("severity")
    attachment_key = event.get("attachment_key") or None

    if not isinstance(title, str) or not title.strip():
        errors.append("title is required")
    elif len(title.strip()) > MAX_TITLE:
        errors.append(f"title must be at most {MAX_TITLE} characters")

    if not isinstance(description, str) or not description.strip():
        errors.append("description is required")
    elif len(description.strip()) > MAX_DESCRIPTION:
        errors.append(f"description must be at most {MAX_DESCRIPTION} characters")

    if not isinstance(severity, str) or severity.strip().lower() not in SEVERITIES:
        errors.append(f"severity must be one of: {', '.join(SEVERITIES)}")

    if attachment_key is not None and (
        not isinstance(attachment_key, str) or not attachment_key.startswith("screenshots/")
    ):
        errors.append("attachment_key must start with 'screenshots/'")

    if errors:
        logger.info("Validation failed: %s", errors)
        return {"valid": False, "errors": errors}

    bug = {
        "bug_id": str(uuid.uuid4()),
        "title": title.strip(),
        "description": description.strip(),
        "severity": severity.strip().lower(),
    }
    if attachment_key:
        bug["attachment_key"] = attachment_key
    return {"valid": True, "errors": [], "bug": bug}

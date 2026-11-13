"""End-to-end tests against a deployed BugSnap stack (real AWS resources, no mocks).

Usage:  python tests/e2e_test.py [stack-name] [region]
Requires AWS credentials (only to read stack outputs and DynamoDB for cleanup).
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
STACK = ARGS[0] if len(ARGS) > 0 else "bugsnap"
REGION = ARGS[1] if len(ARGS) > 1 else "us-east-1"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def outputs():
    out = subprocess.check_output(
        ["aws", "cloudformation", "describe-stacks", "--stack-name", STACK, "--region", REGION,
         "--query", "Stacks[0].Outputs", "--output", "json"], shell=sys.platform == "win32")
    return {o["OutputKey"]: o["OutputValue"] for o in json.loads(out)}


OUT = outputs()
API = OUT["ApiUrl"]
SITE = OUT["WebsiteUrl"]
created = []
results = []
SHELL = sys.platform == "win32"


def call(method, path, body=None, headers=None, url=None):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url or API + path, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), dict(e.headers)
        except ValueError:
            return e.code, raw, dict(e.headers)


def check(name, cond, info=""):
    cond = bool(cond)
    results.append(cond)
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else info)


def main():
    # TC1 validation failure via workflow
    s, b, _ = call("POST", "/bugs", {"title": "", "description": "x", "severity": "nope"})
    check("TC1 invalid bug rejected with 400 + details", s == 400 and b["error"]["code"] == "VALIDATION_FAILED"
          and len(b["error"]["details"]) == 2 and b["workflow"]["status"] == "FAILED", (s, b))

    # TC2 malformed body
    s, b, _ = call("POST", "/bugs", url=API + "/bugs")
    check("TC2 missing body rejected with 400", s == 400, (s, b))

    # TC3 create each severity -> priority mapping through Step Functions
    expected = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}
    ids = {}
    for sev, prio in expected.items():
        s, b, _ = call("POST", "/bugs", {"title": f"E2E {sev} bug", "description": "created by e2e test", "severity": sev})
        ok = s == 201 and b["priority"] == prio and b["workflow"]["status"] == "SUCCEEDED" and b["workflow_status"] == "COMPLETED"
        check(f"TC3 {sev} -> {prio} via workflow", ok, (s, b))
        if s == 201:
            ids[sev] = b["bug_id"]
            created.append(b["bug_id"])

    # TC4 get bug persisted in DynamoDB
    s, b, _ = call("GET", f"/bugs/{ids['critical']}")
    check("TC4 GET /bugs/{id} returns saved item", s == 200 and b["status"] == "open" and b["priority"] == "P1"
          and b["created_at"] and b["updated_at"], (s, b))

    # TC5 404
    s, b, _ = call("GET", "/bugs/does-not-exist")
    check("TC5 unknown id -> 404", s == 404 and b["error"]["code"] == "NOT_FOUND", (s, b))

    # TC6 patch status
    s, b, _ = call("PATCH", f"/bugs/{ids['high']}", {"status": "resolved"})
    check("TC6 PATCH status -> resolved", s == 200 and b["status"] == "resolved", (s, b))
    s, b, _ = call("PATCH", f"/bugs/{ids['high']}", {"status": "bogus"})
    check("TC7 PATCH invalid status -> 400", s == 400, (s, b))
    s, b, _ = call("PATCH", "/bugs/does-not-exist", {"status": "open"})
    check("TC8 PATCH unknown id -> 404", s == 404, (s, b))

    # TC9 list + stats + filters
    s, b, _ = call("GET", "/bugs")
    got = {i["bug_id"] for i in b["bugs"]}
    check("TC9 GET /bugs lists created bugs", s == 200 and set(ids.values()) <= got, (s,))
    st = b["stats"]
    check("TC10 stats consistent", st["total"] == len(b["bugs"]) and st["resolved"] >= 1 and st["open"] >= 3
          and st["high_priority"] >= 1, st)
    s, b, _ = call("GET", "/bugs?severity=critical&status=open")
    check("TC11 filter severity+status", s == 200 and all(i["severity"] == "critical" and i["status"] == "open" for i in b["bugs"])
          and ids["critical"] in {i["bug_id"] for i in b["bugs"]}, (s,))
    s, b, _ = call("GET", "/bugs?severity=wrong")
    check("TC12 invalid filter -> 400", s == 400, (s, b))

    # TC13 screenshot upload to private bucket, then attach to bug
    s, up, _ = call("POST", "/uploads", {"content_type": "image/png"})
    check("TC13 presigned upload URL issued", s == 200 and up["attachment_key"].startswith("screenshots/"), (s, up))
    s, b, _ = call("POST", "/uploads", {"content_type": "text/html"})
    check("TC14 non-image upload rejected", s == 400, (s, b))
    req = urllib.request.Request(up["upload_url"], data=PNG, method="PUT", headers={"Content-Type": "image/png"})
    with urllib.request.urlopen(req) as r:
        check("TC15 PUT screenshot via presigned URL", r.status == 200)
    s, b, _ = call("POST", "/bugs", {"title": "E2E with screenshot", "description": "has attachment", "severity": "low",
                                      "attachment_key": up["attachment_key"]})
    check("TC16 bug created with attachment", s == 201, (s, b))
    if s == 201:
        created.append(b["bug_id"])
        s, full, _ = call("GET", f"/bugs/{b['bug_id']}")
        check("TC17 GET returns presigned attachment_url", s == 200 and "attachment_url" in full, (s, full))
        with urllib.request.urlopen(full["attachment_url"]) as r:
            check("TC18 presigned URL serves the image", r.read() == PNG)
    # private: direct unauthenticated access must fail
    direct = f"https://{OUT['AttachmentBucketName']}.s3.{REGION}.amazonaws.com/{up['attachment_key']}"
    try:
        urllib.request.urlopen(direct)
        check("TC19 attachment not publicly readable", False, "public read succeeded")
    except urllib.error.HTTPError as e:
        check("TC19 attachment not publicly readable", e.code == 403, e.code)

    # TC20 CORS
    for path, method in [("/bugs", "POST"), ("/bugs/x", "PATCH"), ("/uploads", "POST")]:
        s, _, h = call("OPTIONS", path, headers={"Origin": SITE, "Access-Control-Request-Method": method})
        h = {k.lower(): v for k, v in h.items()}
        check(f"TC20 CORS preflight {method} {path}",
              s == 200 and h.get("access-control-allow-origin") == SITE and method in h.get("access-control-allow-methods", ""), (s, h))
    _, _, h = call("GET", "/bugs")
    check("TC21 CORS header on real response", {k.lower(): v for k, v in h.items()}.get("access-control-allow-origin") == SITE)

    # TC22 frontend served from CloudFront over HTTPS
    with urllib.request.urlopen(SITE + "/index.html") as r:
        html = r.read().decode()
    with urllib.request.urlopen(SITE + "/config.js") as r:
        cfg = r.read().decode()
    check("TC22 frontend + config.js served over HTTPS",
          SITE.startswith("https://") and "BugSnap" in html and API in cfg)
    # TC23 frontend bucket is private; only CloudFront can read it
    try:
        urllib.request.urlopen(f"https://{OUT['FrontendBucketName']}.s3.{REGION}.amazonaws.com/index.html")
        check("TC23 frontend bucket not publicly readable", False, "public read succeeded")
    except urllib.error.HTTPError as e:
        check("TC23 frontend bucket not publicly readable", e.code == 403, e.code)
    # TC24 security headers from CloudFront
    with urllib.request.urlopen(SITE + "/") as r:
        hh = {k.lower(): v for k, v in r.headers.items()}
    check("TC24 CloudFront security headers", "strict-transport-security" in hh and "x-content-type-options" in hh, list(hh))


def cleanup():
    # remove test items so the demo table is clean
    for bid in created:
        subprocess.run(["aws", "dynamodb", "delete-item", "--table-name", OUT["TableName"], "--region", REGION,
                        "--key", json.dumps({"bug_id": {"S": bid}})], shell=sys.platform == "win32", check=False)


if __name__ == "__main__":
    try:
        main()
    finally:
        if "--keep" not in sys.argv:
            cleanup()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)

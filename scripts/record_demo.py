"""Record a silent, captioned demo clip of the BugSnap dashboard against the real deployed stack.

Usage:  python scripts/record_demo.py [stack-name] [region] [--keep]

- Drives the live site in Chromium and records a WebM to demo-video/.
- Adds on-screen captions (plain text overlay, no third-party logos or audio).
- Warms the Lambdas first so the recording is not slowed by cold starts.
- Deletes the demo bug it creates afterwards unless --keep is given.
Add your own narration in a video editor (see docs/demo-video-script.md).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zlib

import boto3
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
STACK = ARGS[0] if len(ARGS) > 0 else "bugsnap"
REGION = ARGS[1] if len(ARGS) > 1 else "us-east-1"
KEEP = "--keep" in sys.argv
SHELL = sys.platform == "win32"
W, H = 1440, 900
DEMO_TITLE = "Search results ignore the date filter"
WARM_TITLE = "Warm-up (temporary)"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo-video")


def outputs():
    out = subprocess.check_output(
        ["aws", "cloudformation", "describe-stacks", "--stack-name", STACK, "--region", REGION,
         "--query", "Stacks[0].Outputs", "--output", "json"], shell=SHELL)
    return {o["OutputKey"]: o["OutputValue"] for o in json.loads(out)}


def make_png(path):
    """Small generated image to use as the bug screenshot (an 'error banner' mock)."""
    w, h = 320, 180
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            banner = 40 < x < 280 and 70 < y < 110
            row += bytes((200, 40, 40)) if banner else bytes((235, 238, 245 - y // 6))
        rows.append(bytes(row))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    open(path, "wb").write(png)


def warm_up(api):
    """Warm every Lambda in the workflow. Creates one temporary bug (removed after recording)."""
    def post(body):
        req = urllib.request.Request(api + "/bugs", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req).read()
        except urllib.error.HTTPError:
            pass

    for _ in range(2):
        post({"title": WARM_TITLE, "description": "temporary bug used to warm up the Lambdas", "severity": "low"})
        post({"title": ""})
        urllib.request.urlopen(api + "/bugs").read()


CAPTION_JS = """
(text) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:99999;' +
      'background:rgba(17,24,39,.92);color:#fff;font:600 22px system-ui,sans-serif;padding:12px 22px;' +
      'border-radius:10px;max-width:90%;text-align:center;box-shadow:0 4px 18px rgba(0,0,0,.35);';
    document.body.appendChild(el);
  }
  el.textContent = text;
}
"""


def caption(page, text, hold=2.2):
    page.evaluate(CAPTION_JS, text)
    page.wait_for_timeout(int(hold * 1000))


def remove_bugs(table, titles):
    for it in table.scan()["Items"]:
        if it["title"] in titles:
            table.delete_item(Key={"bug_id": it["bug_id"]})
            print("removed", it["title"], it["bug_id"])


def main():
    out = outputs()
    site, api = out["WebsiteUrl"], out["ApiUrl"]
    print("site:", site)
    table = boto3.resource("dynamodb", region_name=REGION).Table(out["TableName"])
    warm_up(api)
    remove_bugs(table, {WARM_TITLE})  # warm-up bugs must not appear in the recording

    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="bugsnap-rec-")
    png = os.path.join(tmp, "bug-screenshot.png")
    make_png(png)

    with sync_playwright() as p:
        browser = p.chromium.launch(slow_mo=120)
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp,
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.goto(site)
        page.wait_for_selector("#bug-rows tr")
        page.wait_for_function("document.getElementById('stat-total').textContent !== '-'")
        caption(page, "BugSnap: serverless bug tracking on AWS", 3)
        caption(page, "Live counters come from DynamoDB indexes, no table scan", 3)

        # 1. Invalid bug -> workflow fails
        caption(page, "1. Submit an invalid bug: the Step Functions workflow rejects it", 2)
        page.click("#submit-btn")
        page.wait_for_selector("text=Workflow FAILED")
        caption(page, "Validation failed with a clear message and the execution details", 3.5)

        # 2. Valid bug with screenshot -> workflow succeeds
        caption(page, "2. Report a real bug with a screenshot", 2)
        page.fill("#title", "")
        page.type("#title", DEMO_TITLE, delay=35)
        page.type("#description", "Filtering results by date range on the search page still shows items outside the range.", delay=15)
        page.select_option("#severity", "high")
        page.set_input_files("#screenshot", png)
        page.wait_for_timeout(600)
        page.click("#submit-btn")
        page.wait_for_selector("text=Workflow SUCCEEDED", timeout=30000)
        page.wait_for_selector(f"text={DEMO_TITLE}")
        caption(page, "ValidateBug, SaveBug, PrioritizeBug ran: High severity became priority P2", 4)
        caption(page, "Counters updated. The screenshot sits in a private S3 bucket", 3)

        # 3. Update status
        caption(page, "3. Update the status: resolve the bug", 2)
        row = page.locator("#bug-rows tr", has_text=DEMO_TITLE)
        row.locator("select").select_option("resolved")
        page.wait_for_function("document.getElementById('stat-resolved').textContent !== ''")
        page.wait_for_timeout(1800)
        caption(page, "Resolved count went up and the active high-priority count went down", 3.5)

        # 4. Filters
        caption(page, "4. Filter by severity and status", 2)
        page.select_option("#f-severity", "high")
        page.wait_for_timeout(1800)
        page.select_option("#f-status", "open")
        page.wait_for_timeout(1800)
        caption(page, "Each filter is a DynamoDB index query", 2.5)
        page.select_option("#f-severity", "")
        page.select_option("#f-status", "")
        page.wait_for_timeout(1500)
        caption(page, "S3 + CloudFront, API Gateway, Lambda, DynamoDB, Step Functions, CloudWatch. One CloudFormation stack.", 4.5)

        video_path = page.video.path()
        ctx.close()
        browser.close()

    final = os.path.join(OUT_DIR, "bugsnap-dashboard-demo.webm")
    if os.path.exists(final):
        os.remove(final)
    shutil.move(video_path, final)
    shutil.rmtree(tmp, ignore_errors=True)
    print("video:", final, f"({os.path.getsize(final) // 1024} KB)")

    if not KEEP:
        remove_bugs(table, {DEMO_TITLE})


if __name__ == "__main__":
    main()

# Demo video script (target 2:40, hard limit 3:00)

Judges are not required to watch past 3 minutes, so everything important is in the first 2:30.

Rules from the submission requirements:
- Upload it as Public on YouTube, Vimeo, Facebook Video or Youku, and paste the link in the "demo" field.
- No copyrighted music and no third-party logos. Record with no background music; narrate only.
- Show the build running end to end on real AWS (not mock data).

## Before you record

1. The stack is deployed and healthy (checked 13 Nov 2026: `UPDATE_COMPLETE`, 29/29 end-to-end checks pass). Site: https://dz4i01ye2obc7.cloudfront.net
2. The table already has real-looking bugs, so the counters are not zero. Right now: 5 total, 3 open, 1 resolved, 2 high priority. Do not run `tests/e2e_test.py` right before recording.
3. Have a small screenshot file ready (PNG or JPG under 5 MB) that contains no private information.
4. Open these tabs in order: the dashboard, the Step Functions state machine `bugsnap-BugWorkflow` (Executions tab), the CloudWatch log group `/aws/vendedlogs/states/bugsnap-BugWorkflow`, the CloudFormation stack `bugsnap` (Resources tab), and `docs/architecture.png`.
5. Warm up the Lambdas by submitting one bug a minute before recording. After idle time the first run takes about 2.5 seconds because of a cold start; a warm run is about 0.4 to 0.6 seconds.
5. Set the browser zoom so text is readable at 1080p. Close notifications.

## Scripted base clip (optional)

`python scripts/record_demo.py` records a silent 58-second clip of the dashboard against the live stack to `demo-video/bugsnap-dashboard-demo.webm` (1440x900, on-screen captions, no audio). It warms the Lambdas first and deletes the bugs it creates, so your table is unchanged. It covers the first 1:45 of the script below: the failed submission, the successful one with a screenshot, the status change, and the filters. Add your narration in Clipchamp, then record or add the AWS console parts (Step Functions Executions, CloudWatch, CloudFormation) yourself. Pass `--keep` to leave the demo bug in the table. The `demo-video/` folder is git-ignored.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00 to 0:15 | Dashboard, title visible | "Bug reports get lost in chat. BugSnap is a bug tracker with no servers to run: it uses S3 and CloudFront, API Gateway, Lambda, DynamoDB and Step Functions, deployed from one CloudFormation template." |
| 0:15 to 0:30 | `architecture.png` | "The browser loads the site from CloudFront. API calls go through API Gateway to Lambda. Submitting a bug starts a Step Functions workflow that validates, saves and prioritizes it. Screenshots go straight to a private S3 bucket with a presigned URL." |
| 0:30 to 0:55 | Dashboard, submit form: leave the title empty, choose severity, click Submit | "First, a bad report. The title is empty. The workflow rejects it and the API returns a clear error. The Workflow panel shows the execution failed, with its name and duration." |
| 0:55 to 1:30 | Fill title, description, choose High, attach the screenshot, click Submit | "Now a real one. I attach a screenshot. The browser uploads it directly to a private bucket. Then the workflow runs: validate, save to DynamoDB, assign a priority. High severity becomes P2. The panel shows the bug ID, priority and a succeeded workflow, with the duration in milliseconds." |
| 1:30 to 1:55 | Table: new bug at top; counters change; click "View screenshot" | "The bug is in the list and the counters updated: total, open, resolved and high priority. The screenshot opens from a five-minute presigned link. The bucket itself is not public." |
| 1:55 to 2:15 | Change the status of the bug to Resolved; use both filters | "I change the status to resolved. The counters move. Filters for severity and status read from DynamoDB indexes, so listing does not scan the table." |
| 2:15 to 2:35 | Step Functions console, Executions tab (succeeded and failed runs with durations); then the CloudWatch log stream | "Every execution shows up in Step Functions with its status and duration, and the CloudWatch log has the input and output of each state, so I can see exactly where a report failed or succeeded." |
| 2:35 to 2:50 | CloudFormation stack Resources tab | "All of this is one CloudFormation stack, deployed by one script, and removed by another. Idle, it costs about twenty cents a month, mostly CloudWatch alarms. The code, cost breakdown and lessons are in the write-up. Thanks for watching." |

## Tips

- Keep narration calm and short. If a step takes more than a couple of seconds to load, cut or speed it up in editing.
- Do not read the table of numbers aloud. Say the priority mapping once (High becomes P2).
- If the workflow panel is hard to read in the recording, zoom the browser to 125%.
- The only things to say carefully: "about twenty cents a month idle" is an estimate for this stack; do not claim "free".
- Do not show your AWS account ID or access keys. Crop or blur the account menu in the console tabs.

## Backup plan

If CloudFront is slow right after a deploy, open the site after the invalidation finishes (the deploy script prints when it starts). If a test bug is in the way, delete it in the DynamoDB console before recording.

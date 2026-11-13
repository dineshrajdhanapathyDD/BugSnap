# BugSnap cost analysis

Region: us-east-1. Prices read from the AWS Price List API on 13 Nov 2026. Everything under "Estimate" is arithmetic on stated assumptions, not a bill.

## Verified unit prices (AWS Price List API, 13 Nov 2026)

| Service | Price | Notes |
|---|---|---|
| API Gateway REST | $3.50 per million requests | first 333 million per month |
| Lambda requests | $0.20 per million | us-east-1 |
| Lambda compute | $0.0000166667 per GB-second (x86, first 6 billion GB-s) | Read from the Price List rows for us-east-2 and other regions; the us-east-1 x86 row did not come back from my query. us-east-1 ARM is $0.0000133334. Free tier: 400,000 GB-seconds |
| Step Functions Express | $1.00 per million requests, plus $0.00001667 per GB-second (first 3.6 million GB-s) | us-east-1 |
| DynamoDB on-demand | $0.625 per million write units, $0.125 per million read units | us-east-1 |
| DynamoDB storage | first 25 GB-month free, then $0.25 per GB-month | |
| DynamoDB point-in-time recovery | $0.20 per GB-month | |
| S3 Standard | $0.023 per GB-month (first 50 TB) | |
| CloudFront | $0.01 per 10,000 HTTPS requests (US request tier) | Data transfer out and any free tier were not checked |
| CloudWatch alarm | $0.10 per standard alarm per month | |
| CloudWatch Logs | $0.50 per GB ingested, $0.03 per GB-month stored | |

Not priced: CloudFront data transfer, API Gateway and CloudFront free tiers, S3 request charges. All of these are small at this scale.

## Measured usage (CloudWatch, from my test runs on the live stack)

| Function | Invocations | Average | Slowest |
|---|---|---|---|
| CreateBug | 44 | 398 ms | 3,015 ms (cold start) |
| ValidateBug | 38 | 4.7 ms | 47 ms |
| SaveBug | 31 | 102 ms | 543 ms |
| PrioritizeBug | 31 | 112 ms | 631 ms |
| GetBugs | 30 | 98 ms | 444 ms |
| GetBug | 21 | 107 ms | 308 ms |
| UpdateBug | 20 | 136 ms | 509 ms |
| GetUploadUrl | 14 | 17 ms | 51 ms |

Step Functions: 38 Express executions, average 398 ms. The table held 6 items (1,379 bytes) when I read it.

## Estimate: what a month costs

Assumptions: Lambda at the deployed memory sizes (128 MB, GetBugs 256 MB) and the measured average durations above; Express workflow billed at 64 MB; about 4 files per page load through CloudFront; items about 0.5 KB.

DynamoDB write units per bug: creating a bug writes the item plus two global secondary indexes (3 units), setting the priority writes the same again (3 units), and each status change touches both indexes (about 4 units). That is roughly 10 write units per bug.

| | Idle | Light: 1,000 bugs, 5,000 dashboard loads | Moderate: 10,000 bugs, 50,000 dashboard loads |
|---|---|---|---|
| API Gateway | $0 | $0.02 | $0.25 |
| Lambda requests + compute | $0 | $0.01 | $0.06 (compute is inside the free tier) |
| Step Functions Express | $0 | $0.00 | $0.02 |
| DynamoDB writes | $0 | $0.01 | $0.06 |
| CloudFront requests | $0 | $0.02 | $0.20 |
| CloudWatch Logs | $0 | ~$0.00 | ~$0.02 |
| CloudWatch alarms (2) | $0.20 | $0.20 | $0.20 |
| **Total** | **about $0.20** | **about $0.26** | **about $0.81 + dashboard stats reads** |

The only cost that exists with zero traffic is the two alarms. DynamoDB storage, point-in-time recovery and S3 storage on a few KB are effectively $0.

### The cost that grows with data: dashboard stats

`GET /bugs` counts bugs with DynamoDB COUNT queries. A COUNT query is still billed for the data it reads. With 10,000 stored bugs the counts read up to about 5 to 10 MB per dashboard load, which is roughly 1,300 read units. At 50,000 loads that is about 65 million read units, or **up to roughly $8 per month** (estimate, eventually consistent reads). With a few hundred bugs it is cents.

Fix when it matters: keep running counters in one DynamoDB item, updated by SaveBug and UpdateBug (or a DynamoDB Streams consumer), so stats cost one read.

## Cost levers

- Switch the Lambda functions to ARM (Graviton): compute is about 20% cheaper per GB-second ($0.0000133334 vs $0.0000166667).
- Drop `IncludeExecutionData` from the state machine logging if the logs grow.
- Delete the point-in-time recovery setting if you do not need it.
- `scripts/cleanup.ps1` removes everything, so a demo costs nothing after teardown.

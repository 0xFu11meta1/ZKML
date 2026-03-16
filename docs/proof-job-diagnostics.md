# Proof Job Diagnostics

Use this flow for any `failed` or `timeout` proof job.

## 1. Fetch Job and Partition State

```bash
curl -sf "http://localhost:8000/proofs/jobs/<task_id>" | jq
curl -sf "http://localhost:8000/proofs/jobs/<task_id>/partitions" | jq
```

## 2. Classify Failure

- `No online provers available`: prover fleet availability issue.
- `Dispatch timed out`: worker saturation or DB lock/contention.
- `Aggregation error`: missing/invalid proof fragments or IPFS retrieval errors.
- `Proving timed out`: prover capacity/performance issue.

## 3. Recovery Actions

1. If job is terminal and customer impact exists, resubmit proof request.
2. If many jobs share same failure, escalate to incident and pause new submissions.
3. For webhook-only failures, do not rerun proving; replay webhook delivery only.

## 4. Data to Capture for RCA

- `task_id`, `job_id`, `status`, `error`.
- Queue depth and worker count at failure time.
- IPFS/API latency and DB connection stats.
- Prover online count and benchmark distribution.

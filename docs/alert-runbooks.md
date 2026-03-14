# Alert Runbooks

Map alerts from `docker/prometheus/alerts.yml` to concrete actions.

## NoOnlineProvers

1. Check prover heartbeat freshness in DB and logs.
2. Run prover health task manually.
3. Restart worker if stale status persists.

```bash
docker compose exec worker celery -A registry.tasks.celery_app.app call registry.tasks.prover_health.check_prover_health
```

## ProofQueueBacklogHigh

1. Confirm queue depth.
2. Scale workers.
3. Inspect slow external dependencies (IPFS/DB).

## ProofTimeoutRateHigh

1. Identify dominant timeout stage (`dispatched` vs `proving`).
2. Check prover availability and benchmark skew.
3. Validate IPFS latency and DB contention.

## WebhookDeliveryFailures

1. Inspect webhook endpoint failures in worker logs.
2. Disable repeatedly failing webhook configs.
3. Notify affected tenant.

## DatabaseConnectionSaturation

1. Check active DB sessions.
2. Reduce worker concurrency temporarily.
3. Scale DB or add pooling (pgbouncer) as follow-up.
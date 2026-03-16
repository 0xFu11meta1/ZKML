# Celery Operations Runbook

## 1. Inspect Worker Health

```bash
docker compose ps worker beat redis
curl -sf http://localhost:5555/api/workers | jq
```

## 2. Inspect Queue Backlog

```bash
docker compose exec redis redis-cli LLEN celery
curl -sf http://localhost:5555/api/tasks?state=STARTED | jq
```

## 3. Stuck Task Recovery

1. Identify task type and count in Flower.
2. Restart worker first:

```bash
docker compose restart worker
```

3. If queue remains blocked, purge only after approval:

```bash
docker compose exec worker celery -A registry.tasks.celery_app.app purge -f
```

4. Trigger health sweep after recovery:

```bash
docker compose exec worker celery -A registry.tasks.celery_app.app call registry.tasks.prover_health.cleanup_stale_jobs
```

## 4. Scale Workers

```bash
docker compose up -d --scale worker=4
```

Target trigger: sustained queue depth above 100 for > 5 minutes.

## 5. Post-Recovery Validation

- `/health/ready` is healthy.
- Queue depth decreases.
- New proof jobs transition out of `queued` and `dispatched`.

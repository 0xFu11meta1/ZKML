# IPFS Operations Runbook

## 1. Basic Health Checks

```bash
curl -sf http://127.0.0.1:5001/api/v0/version
curl -sf http://127.0.0.1:5001/api/v0/id
docker compose logs --tail=200 ipfs
```

## 2. Diagnose Upload/Download Failures

1. Check API reachability from `registry` container.
2. Verify CID format and pin status.

```bash
docker compose exec registry python - <<'PY'
import httpx
print(httpx.post('http://ipfs:5001/api/v0/version', timeout=5).status_code)
PY
```

## 3. Safe Maintenance

Run garbage collection only in maintenance windows:

```bash
docker compose exec ipfs ipfs repo gc
```

Check repo stats:

```bash
docker compose exec ipfs ipfs repo stat
```

## 4. Outage Recovery

1. Restart IPFS container.
2. Re-run health checks.
3. Requeue failed proof jobs if needed via Celery operations.

```bash
docker compose restart ipfs
```

## 5. Security Requirements

- Do not expose port `5001` publicly.
- Keep API bound to localhost/internal network only.
- Restrict CORS origins for IPFS API.

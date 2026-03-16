# Database Migration Runbook

## Scope

Safe execution and rollback of Alembic migrations in production.

## 1. Pre-Migration Checklist

1. Confirm clean git revision and release tag.
2. Take a backup:

```bash
./scripts/backup.sh ./backups
```

3. Confirm DB connectivity:

```bash
docker compose exec registry alembic current
```

## 2. Apply Migration

```bash
docker compose exec registry alembic upgrade head
```

## 3. Verify Migration

```bash
docker compose exec registry alembic current
docker compose exec registry python - <<'PY'
from registry.core.deps import sync_engine
with sync_engine.connect() as c:
    print('db ok:', c.exec_driver_sql('select 1').scalar())
PY
```

## 4. Rollback Procedure

If deploy health checks fail immediately after migration:

```bash
docker compose exec registry alembic downgrade -1
docker compose restart registry worker beat
```

If downgrade fails:

1. Restore latest PostgreSQL backup:

```bash
./scripts/restore.sh pg backups/<latest>.dump
```

2. Redeploy last known-good application image.

## 5. Common Failure Modes

- `Multiple head revisions`: run `alembic heads` and resolve before deploy.
- Lock timeout / long-running migration: pause writes and retry.
- Data constraint violations: patch offending rows in maintenance window, rerun migration.

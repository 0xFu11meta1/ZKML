"""Tests for /audit API routes — list, filter, CSV export."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

_HOTKEY = "5FAuditTestUserXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

_nonce_seq = 0


def _auth(hotkey: str = _HOTKEY) -> dict:
    global _nonce_seq
    _nonce_seq += 1
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


async def _seed_audit_logs(client: AsyncClient):
    """Create an org which produces an audit log entry."""
    await client.post(
        "/orgs",
        json={"name": "Audit Test Org", "slug": "audit-test-org"},
        headers=_auth(),
    )


class TestListAuditLogs:
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/audit", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_requires_auth(self, client: AsyncClient):
        resp = await client.get("/audit")
        assert resp.status_code == 422

    async def test_list_after_org_create(self, client: AsyncClient):
        await _seed_audit_logs(client)
        resp = await client.get("/audit", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        actions = [item["action"] for item in data["items"]]
        assert "org.created" in actions

    async def test_filter_by_action(self, client: AsyncClient):
        await _seed_audit_logs(client)
        resp = await client.get("/audit?action=org.created", headers=_auth())
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["action"] == "org.created"

    async def test_filter_by_actor(self, client: AsyncClient):
        await _seed_audit_logs(client)
        resp = await client.get(f"/audit?actor_hotkey={_HOTKEY}", headers=_auth())
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["actor_hotkey"] == _HOTKEY

    async def test_pagination(self, client: AsyncClient):
        await _seed_audit_logs(client)
        resp = await client.get("/audit?page=1&page_size=1", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 1


class TestExportAuditCSV:
    async def test_export_requires_auth(self, client: AsyncClient):
        resp = await client.get("/audit/export")
        assert resp.status_code == 422

    async def test_export_csv(self, client: AsyncClient):
        await _seed_audit_logs(client)
        resp = await client.get("/audit/export", headers=_auth())
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        text = resp.text
        lines = text.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 data row
        assert "id" in lines[0]
        assert "action" in lines[0]

"""Tests for /api-keys API routes — create, list, revoke."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

_HOTKEY = "5FApiKeyUserXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
_OTHER_HOTKEY = "5FOtherKeyUserXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

_nonce_seq = 0


def _auth(hotkey: str = _HOTKEY) -> dict:
    global _nonce_seq
    _nonce_seq += 1
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


class TestCreateAPIKey:
    async def test_create_default(self, client: AsyncClient):
        resp = await client.post("/api-keys", json={}, headers=_auth())
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"].startswith("mnn_")
        assert data["daily_limit"] == 1000
        assert data["requests_today"] == 0
        assert data["id"] > 0

    async def test_create_with_label(self, client: AsyncClient):
        resp = await client.post(
            "/api-keys",
            json={"label": "ci-bot", "daily_limit": 500},
            headers=_auth(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "ci-bot"
        assert data["daily_limit"] == 500

    async def test_create_unauthenticated_422(self, client: AsyncClient):
        resp = await client.post("/api-keys", json={})
        assert resp.status_code == 422


class TestListAPIKeys:
    async def test_list_own_keys(self, client: AsyncClient):
        await client.post("/api-keys", json={"label": "key-a"}, headers=_auth())
        await client.post("/api-keys", json={"label": "key-b"}, headers=_auth())
        resp = await client.get("/api-keys", headers=_auth())
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) >= 2
        labels = {k["label"] for k in keys}
        assert "key-a" in labels
        assert "key-b" in labels

    async def test_keys_scoped_to_user(self, client: AsyncClient):
        await client.post("/api-keys", json={"label": "mine"}, headers=_auth())
        await client.post("/api-keys", json={"label": "theirs"}, headers=_auth(_OTHER_HOTKEY))
        resp = await client.get("/api-keys", headers=_auth())
        labels = {k["label"] for k in resp.json()}
        assert "mine" in labels
        assert "theirs" not in labels


class TestRevokeAPIKey:
    async def test_revoke_own_key(self, client: AsyncClient):
        create_resp = await client.post("/api-keys", json={"label": "trash"}, headers=_auth())
        key_id = create_resp.json()["id"]
        resp = await client.delete(f"/api-keys/{key_id}", headers=_auth())
        assert resp.status_code == 204
        # Verify it's gone
        keys = (await client.get("/api-keys", headers=_auth())).json()
        assert all(k["id"] != key_id for k in keys)

    async def test_revoke_nonexistent_404(self, client: AsyncClient):
        resp = await client.delete("/api-keys/99999", headers=_auth())
        assert resp.status_code == 404

    async def test_cannot_revoke_others_key(self, client: AsyncClient):
        create_resp = await client.post("/api-keys", json={}, headers=_auth())
        key_id = create_resp.json()["id"]
        resp = await client.delete(f"/api-keys/{key_id}", headers=_auth(_OTHER_HOTKEY))
        assert resp.status_code == 404


class TestAPIKeyExpiration:
    async def test_create_with_expiration(self, client: AsyncClient):
        resp = await client.post(
            "/api-keys",
            json={"label": "expiring", "expires_in_days": 30},
            headers=_auth(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["expires_at"] is not None

    async def test_create_without_expiration(self, client: AsyncClient):
        resp = await client.post(
            "/api-keys",
            json={"label": "permanent"},
            headers=_auth(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["expires_at"] is None

    async def test_expires_in_days_bounds(self, client: AsyncClient):
        resp = await client.post(
            "/api-keys",
            json={"label": "bad", "expires_in_days": 0},
            headers=_auth(),
        )
        assert resp.status_code == 422

        resp = await client.post(
            "/api-keys",
            json={"label": "bad", "expires_in_days": 400},
            headers=_auth(),
        )
        assert resp.status_code == 422

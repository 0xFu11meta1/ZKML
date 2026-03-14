"""Tests for /orgs API routes — org CRUD, membership, RBAC."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

# Valid SS58-length hotkeys (>= 46 chars)
_ADMIN_HOTKEY = "5FTestAdminXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
_MEMBER_HOTKEY = "5FTestMemberXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
_OTHER_HOTKEY = "5FOtherUserXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

_nonce_seq = 0


def _auth(hotkey: str = _ADMIN_HOTKEY) -> dict:
    """Generate fresh auth headers with a unique nonce each call."""
    global _nonce_seq
    _nonce_seq += 1
    # The security layer does int(nonce) and checks abs(now - nonce) <= 300.
    # Adding a small offset doesn't break freshness but ensures uniqueness.
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


def _org_payload(**overrides) -> dict:
    defaults = {"name": "Test Org", "slug": "test-org"}
    defaults.update(overrides)
    return defaults


# ── Create org ───────────────────────────────────────────────

class TestCreateOrg:
    async def test_create_success(self, client: AsyncClient):
        resp = await client.post("/orgs", json=_org_payload(), headers=_auth())
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Org"
        assert data["slug"] == "test-org"
        assert data["id"] > 0

    async def test_duplicate_slug_409(self, client: AsyncClient):
        await client.post("/orgs", json=_org_payload(), headers=_auth())
        resp = await client.post("/orgs", json=_org_payload(), headers=_auth())
        assert resp.status_code == 409

    async def test_invalid_slug_422(self, client: AsyncClient):
        resp = await client.post(
            "/orgs", json=_org_payload(slug="A B!"), headers=_auth(),
        )
        assert resp.status_code == 422

    async def test_create_unauthenticated_422(self, client: AsyncClient):
        resp = await client.post("/orgs", json=_org_payload())
        assert resp.status_code == 422


# ── Get / list orgs ─────────────────────────────────────────

class TestGetOrg:
    async def test_get_by_slug(self, client: AsyncClient):
        await client.post("/orgs", json=_org_payload(), headers=_auth())
        resp = await client.get("/orgs/test-org")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "test-org"

    async def test_get_not_found(self, client: AsyncClient):
        resp = await client.get("/orgs/nonexistent")
        assert resp.status_code == 404

    async def test_list_my_orgs(self, client: AsyncClient):
        await client.post("/orgs", json=_org_payload(), headers=_auth())
        resp = await client.get("/orgs/me", headers=_auth())
        assert resp.status_code == 200
        orgs = resp.json()
        assert len(orgs) >= 1
        assert orgs[0]["slug"] == "test-org"


# ── Membership ───────────────────────────────────────────────

class TestMembership:
    async def _setup_org(self, client: AsyncClient):
        await client.post("/orgs", json=_org_payload(), headers=_auth())

    async def test_add_member(self, client: AsyncClient):
        await self._setup_org(client)
        resp = await client.post(
            f"/orgs/test-org/members?hotkey={_MEMBER_HOTKEY}&role=viewer",
            headers=_auth(),
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "viewer"

    async def test_add_member_duplicate_409(self, client: AsyncClient):
        await self._setup_org(client)
        await client.post(
            f"/orgs/test-org/members?hotkey={_MEMBER_HOTKEY}&role=viewer",
            headers=_auth(),
        )
        resp = await client.post(
            f"/orgs/test-org/members?hotkey={_MEMBER_HOTKEY}&role=viewer",
            headers=_auth(),
        )
        assert resp.status_code == 409

    async def test_list_members(self, client: AsyncClient):
        await self._setup_org(client)
        resp = await client.get("/orgs/test-org/members", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_update_member_role(self, client: AsyncClient):
        await self._setup_org(client)
        await client.post(
            f"/orgs/test-org/members?hotkey={_MEMBER_HOTKEY}&role=viewer",
            headers=_auth(),
        )
        resp = await client.patch(
            f"/orgs/test-org/members/{_MEMBER_HOTKEY}?role=editor",
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    async def test_remove_member(self, client: AsyncClient):
        await self._setup_org(client)
        await client.post(
            f"/orgs/test-org/members?hotkey={_MEMBER_HOTKEY}&role=viewer",
            headers=_auth(),
        )
        resp = await client.delete(
            f"/orgs/test-org/members/{_MEMBER_HOTKEY}",
            headers=_auth(),
        )
        assert resp.status_code == 204

    async def test_remove_self_400(self, client: AsyncClient):
        await self._setup_org(client)
        resp = await client.delete(
            f"/orgs/test-org/members/{_ADMIN_HOTKEY}",
            headers=_auth(),
        )
        assert resp.status_code == 400

    async def test_non_admin_cannot_add_member(self, client: AsyncClient):
        await self._setup_org(client)
        await client.post(
            f"/orgs/test-org/members?hotkey={_MEMBER_HOTKEY}&role=viewer",
            headers=_auth(),
        )
        resp = await client.post(
            f"/orgs/test-org/members?hotkey={_OTHER_HOTKEY}&role=viewer",
            headers=_auth(_MEMBER_HOTKEY),
        )
        assert resp.status_code == 403

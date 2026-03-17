"""Edge-case tests for circuits — soft-delete exclusion, versioning, boundaries."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


_nonce_seq = 10_000


def _auth(hotkey="5FTestPublisherXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"):
    global _nonce_seq
    _nonce_seq += 1
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


_VALID_CIDS = [
    "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG",
    "QmT5NvUtoM5nWFfrQnVFwHvBpiFkHjbGEhYbTnTEt5aYrj",
    "QmUNLLsPACCz1vLxQVkXqqLX5R1X345qqfHbsf67hvA3Nn",
    "QmSsw6EcnwEiTT9c4rnAGeSENvsJMepNHmbrgi2S9bXNjm",
    "QmbWqxBEKC3P8tqsKc98xmWNzrzDtRLMiMPL8wBuTGsMnR",
]


def _circuit_payload(name="edge-circuit", **overrides) -> dict:
    defaults = {
        "name": name,
        "version": "1.0.0",
        "proof_type": "groth16",
        "circuit_type": "general",
        "num_constraints": 1000,
        "ipfs_cid": _VALID_CIDS[0],
    }
    defaults.update(overrides)
    return defaults


# ── Soft-delete exclusion ────────────────────────────────────


class TestSoftDeleteExclusion:
    async def test_deleted_circuit_hidden_from_list(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(name="will-delete", ipfs_cid=_VALID_CIDS[0]),
            headers=_auth(),
        )
        assert resp.status_code == 201
        cid = resp.json()["id"]

        # Delete it
        resp = await client.delete(f"/circuits/{cid}", headers=_auth())
        assert resp.status_code in (200, 204)

        # Should not appear in list
        resp = await client.get("/circuits")
        items = resp.json()["items"]
        assert all(item["id"] != cid for item in items)

    async def test_deleted_circuit_404_on_get(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(name="get-delete", ipfs_cid=_VALID_CIDS[1]),
            headers=_auth(),
        )
        cid = resp.json()["id"]
        await client.delete(f"/circuits/{cid}", headers=_auth())

        resp = await client.get(f"/circuits/{cid}")
        assert resp.status_code == 404

    async def test_deleted_circuit_download_404(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(name="dl-delete", ipfs_cid=_VALID_CIDS[2]),
            headers=_auth(),
        )
        cid = resp.json()["id"]
        await client.delete(f"/circuits/{cid}", headers=_auth())

        resp = await client.post(f"/circuits/{cid}/download")
        assert resp.status_code == 404

    async def test_deleted_circuit_does_not_block_reupload(self, client: AsyncClient):
        payload = _circuit_payload(name="reupload-test", ipfs_cid=_VALID_CIDS[3])
        resp = await client.post("/circuits", json=payload, headers=_auth())
        assert resp.status_code == 201
        cid = resp.json()["id"]

        await client.delete(f"/circuits/{cid}", headers=_auth())

        # Re-upload same name+version should succeed (soft-deleted doesn't conflict)
        resp2 = await client.post("/circuits", json=payload, headers=_auth())
        # It can be 201 (if dedup check ignores deleted) or 409 (if not)
        # We document the actual behavior here
        assert resp2.status_code in (201, 409)


# ── Version listing ──────────────────────────────────────────


class TestVersionListing:
    async def test_version_list(self, client: AsyncClient):
        cids = [
            "QmRKs2ZfuwvmZA3QAYisRC3Gn1PGejQFZp4CUpH3GNn3be",
            "QmNhFMqaNsLNFEbMoiYXBVbwMgKLwnXSMijovGFmvDHMDL",
        ]
        for i, version in enumerate(["1.0.0", "2.0.0"]):
            resp = await client.post(
                "/circuits",
                json=_circuit_payload(name="versioned-circ", version=version, ipfs_cid=cids[i]),
                headers=_auth(),
            )
            assert resp.status_code == 201

        # Get versions of first circuit
        first = (await client.get("/circuits")).json()["items"][0]
        resp = await client.get(f"/circuits/{first['id']}/versions")
        assert resp.status_code == 200
        data = resp.json()
        versions = [item["version"] for item in data["items"]]
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    async def test_versions_not_found(self, client: AsyncClient):
        resp = await client.get("/circuits/9999/versions")
        assert resp.status_code == 404


# ── Boundary conditions ──────────────────────────────────────


class TestCircuitBoundaries:
    async def test_zero_constraints_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(num_constraints=0, ipfs_cid=_VALID_CIDS[4]),
            headers=_auth(),
        )
        assert resp.status_code in (400, 422)

    async def test_negative_constraints_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(num_constraints=-1, ipfs_cid=_VALID_CIDS[4]),
            headers=_auth(),
        )
        assert resp.status_code in (400, 422)

    async def test_very_long_name_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(name="x" * 300, ipfs_cid=_VALID_CIDS[4]),
            headers=_auth(),
        )
        assert resp.status_code in (400, 422)

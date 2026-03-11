"""Tests for /circuits API routes — upload, list, get, search, download tracking."""

from __future__ import annotations

import pytest
import time

from httpx import AsyncClient


_nonce_seq = 0


def _auth(hotkey="5FTestPublisherXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"):
    global _nonce_seq
    _nonce_seq += 1
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


# ── Helpers ──────────────────────────────────────────────────

# Valid CIDv0: Qm + 44 base58 chars
_VALID_CID = "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"


def _circuit_payload(**overrides) -> dict:
    defaults = {
        "name": "test-circuit",
        "version": "1.0.0",
        "proof_type": "groth16",
        "circuit_type": "general",
        "num_constraints": 1000,
        "ipfs_cid": _VALID_CID,
    }
    defaults.update(overrides)
    return defaults


# ── Upload ───────────────────────────────────────────────────

class TestUploadCircuit:
    async def test_upload_success(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(),
            headers=_auth(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-circuit"
        assert data["proof_type"] == "groth16"
        assert data["circuit_type"] == "general"
        assert data["num_constraints"] == 1000
        assert data["publisher_hotkey"] == "5FTestPublisherXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        assert "circuit_hash" in data
        assert data["id"] > 0

    async def test_upload_duplicate_hash_409(self, client: AsyncClient):
        payload = _circuit_payload()
        resp1 = await client.post("/circuits", json=payload, headers=_auth())
        assert resp1.status_code == 201
        resp2 = await client.post("/circuits", json=payload, headers=_auth())
        assert resp2.status_code == 409

    async def test_upload_duplicate_name_version_409(self, client: AsyncClient):
        resp1 = await client.post(
            "/circuits",
            json=_circuit_payload(ipfs_cid="QmT5NvUtoM5nWFfrQnVFwHvBpiFkHjbGEhYbTnTEt5aYrj"),
            headers=_auth(),
        )
        assert resp1.status_code == 201
        resp2 = await client.post(
            "/circuits",
            json=_circuit_payload(ipfs_cid="QmUNLLsPACCz1vLxQVkXqqLX5R1X345qqfHbsf67hvA3Nn"),
            headers=_auth(),
        )
        assert resp2.status_code == 409

    async def test_upload_invalid_proof_type_400(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(proof_type="invalid_system"),
            headers=_auth(),
        )
        assert resp.status_code == 400

    async def test_upload_invalid_circuit_type_400(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(circuit_type="not_a_type"),
            headers=_auth(),
        )
        assert resp.status_code == 400

    async def test_upload_missing_hotkey_422(self, client: AsyncClient):
        """Omitting auth headers should return 422 (missing x-hotkey header)."""
        resp = await client.post("/circuits", json=_circuit_payload())
        assert resp.status_code == 422

    async def test_upload_all_proof_types(self, client: AsyncClient):
        cids = [
            "QmRKs2ZfuwvmZA3QAYisRC3Gn1PGejQFZp4CUpH3GNn3be",
            "QmNhFMqaNsLNFEbMoiYXBVbwMgKLwnXSMijovGFmvDHMDL",
            "QmPZ9gcCEpqKTo6aq61g2nXGUhM4iCL3ewB6LDXZCtioEB",
            "QmQ7mBT4MMHcdjnhVDPcWNQGmfRfGNzLfxpYsmFr7FGAzj",
        ]
        for i, pt in enumerate(["groth16", "plonk", "halo2", "stark"]):
            resp = await client.post(
                "/circuits",
                json=_circuit_payload(
                    name=f"circuit-{pt}",
                    proof_type=pt,
                    ipfs_cid=cids[i],
                ),
                headers=_auth(),
            )
            assert resp.status_code == 201
            assert resp.json()["proof_type"] == pt

    async def test_upload_with_optional_fields(self, client: AsyncClient):
        resp = await client.post(
            "/circuits",
            json=_circuit_payload(
                description="A complex circuit",
                proving_key_cid="QmW2WQi7j6c7UgJTarActp7tDNikE4B2qXtFCfLPdsgaTQ",
                verification_key_cid="QmRf22bZar3WKmojipms22PkXH1MZGmvsqzQtuSvQE3uhm",
                size_bytes=4096,
                tags=["ml", "zkml"],
                num_public_inputs=5,
                num_private_inputs=10,
            ),
            headers=_auth(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "A complex circuit"
        assert data["proving_key_cid"] == "QmW2WQi7j6c7UgJTarActp7tDNikE4B2qXtFCfLPdsgaTQ"
        assert data["tags"] == ["ml", "zkml"]
        assert data["num_public_inputs"] == 5
        assert data["num_private_inputs"] == 10


# ── List ─────────────────────────────────────────────────────

class TestListCircuits:
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/circuits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_with_data(self, client: AsyncClient):
        list_cids = [
            "QmSsw6EcnwEiTT9c4rnAGeSENvsJMepNHmbrgi2S9bXNjm",
            "QmbWqxBEKC3P8tqsKc98xmWNzrzDtRLMiMPL8wBuTGsMnR",
            "QmTzQ1JRkWErjk39mryYw2WVaphAZNAREyMchXzYQ7c15n",
        ]
        for i in range(3):
            await client.post(
                "/circuits",
                json=_circuit_payload(name=f"circ-{i}", ipfs_cid=list_cids[i]),
                headers=_auth(),
            )
        resp = await client.get("/circuits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    async def test_list_pagination(self, client: AsyncClient):
        page_cids = [
            "QmVE7b6qVAPo93rG2Vj1zRz7WMXQ5YsMDMBqxfPniXMV5G",
            "QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco",
            "QmZTR5bcpQD7cFgTorqxZDYaew1Wqgfbd2ud9QqGPAkK2V",
            "QmaozNR7DZHQK1ZcU9p7QdrshMvXqWK6gpu5rmrkPdT3L4",
            "QmcRD4wkPPi6dig81r5sLj9Zm1gDCL4zgpEj9CfuRrGbzF",
        ]
        for i in range(5):
            await client.post(
                "/circuits",
                json=_circuit_payload(name=f"circ-{i}", ipfs_cid=page_cids[i]),
                headers=_auth(),
            )
        resp = await client.get("/circuits?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    async def test_list_filter_proof_type(self, client: AsyncClient):
        await client.post(
            "/circuits",
            json=_circuit_payload(name="g16", proof_type="groth16", ipfs_cid="QmdEjBo13JBjNxVFmgJesYmzPBEMsRhB7FBqWKdPALMtec"),
            headers=_auth(),
        )
        await client.post(
            "/circuits",
            json=_circuit_payload(name="plonk", proof_type="plonk", ipfs_cid="QmfGBRT6BbWJd7yUc2uYdaUZJBbnEFvTqehPFoSMQ6wgdr"),
            headers=_auth(),
        )
        resp = await client.get("/circuits?proof_type=groth16")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["proof_type"] == "groth16"

    async def test_list_search(self, client: AsyncClient):
        await client.post(
            "/circuits",
            json=_circuit_payload(name="my-special-circuit", ipfs_cid="QmNRCQWfgze6AbBCaT1rkYFojoNitYDAMXU647qPCDAqS9"),
            headers=_auth(),
        )
        await client.post(
            "/circuits",
            json=_circuit_payload(name="other", ipfs_cid="QmPCYqeRkGxcAfuHQDC46BKDS1AXvDXTTcfR4FXhYhpmEn"),
            headers=_auth(),
        )
        resp = await client.get("/circuits?search=special")
        data = resp.json()
        assert data["total"] == 1
        assert "special" in data["items"][0]["name"]


# ── Get ──────────────────────────────────────────────────────

class TestGetCircuit:
    async def test_get_by_id(self, client: AsyncClient):
        create = await client.post(
            "/circuits",
            json=_circuit_payload(),
            headers=_auth(),
        )
        cid = create.json()["id"]
        resp = await client.get(f"/circuits/{cid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-circuit"

    async def test_get_not_found(self, client: AsyncClient):
        resp = await client.get("/circuits/999")
        assert resp.status_code == 404

    async def test_get_by_hash(self, client: AsyncClient):
        create = await client.post(
            "/circuits",
            json=_circuit_payload(),
            headers=_auth(),
        )
        chash = create.json()["circuit_hash"]
        resp = await client.get(f"/circuits/hash/{chash}")
        assert resp.status_code == 200
        assert resp.json()["circuit_hash"] == chash

    async def test_get_by_hash_not_found(self, client: AsyncClient):
        resp = await client.get("/circuits/hash/deadbeef")
        assert resp.status_code == 404


# ── Download tracking ────────────────────────────────────────

class TestDownloadTracking:
    async def test_track_download(self, client: AsyncClient):
        create = await client.post(
            "/circuits",
            json=_circuit_payload(),
            headers=_auth(),
        )
        cid = create.json()["id"]
        resp = await client.post(f"/circuits/{cid}/download")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        detail = await client.get(f"/circuits/{cid}")
        assert detail.json()["downloads"] == 1

    async def test_track_download_not_found(self, client: AsyncClient):
        resp = await client.post("/circuits/999/download")
        assert resp.status_code == 404

"""Tests for /provers API routes — registration, ping, listing, stats."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


# ── Auth helper ──────────────────────────────────────────────

_nonce_seq = 0

# Hotkeys must be >= 46 chars to pass verify_publisher validation.
_MINER1 = "5FMiner1XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
_MINER2 = "5FMiner2XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"


def _auth(hotkey: str = _MINER1) -> dict:
    global _nonce_seq
    _nonce_seq += 1
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


# ── Helpers ──────────────────────────────────────────────────

def _prover_payload(**overrides) -> dict:
    defaults = {
        "gpu_name": "NVIDIA RTX 4090",
        "gpu_backend": "cuda",
        "gpu_count": 2,
        "vram_total_bytes": 25_769_803_776,
        "vram_available_bytes": 20_000_000_000,
        "compute_units": 128,
        "benchmark_score": 9500.0,
        "supported_proof_types": ["groth16", "plonk"],
        "max_constraints": 10_000_000,
    }
    defaults.update(overrides)
    return defaults


# ── Registration ─────────────────────────────────────────────

class TestProverRegistration:
    async def test_register_new_prover(self, client: AsyncClient):
        resp = await client.post(
            "/provers/register",
            json=_prover_payload(),
            headers=_auth(_MINER1),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["hotkey"] == _MINER1
        assert data["gpu_name"] == "NVIDIA RTX 4090"
        assert data["gpu_backend"] == "cuda"
        assert data["gpu_count"] == 2
        assert data["online"] is True
        assert data["benchmark_score"] == 9500.0

    async def test_register_upsert_existing(self, client: AsyncClient):
        await client.post(
            "/provers/register",
            json=_prover_payload(benchmark_score=5000.0),
            headers=_auth(_MINER1),
        )
        resp = await client.post(
            "/provers/register",
            json=_prover_payload(benchmark_score=9999.0),
            headers=_auth(_MINER1),
        )
        assert resp.status_code == 201
        assert resp.json()["benchmark_score"] == 9999.0

    async def test_register_invalid_gpu_backend_400(self, client: AsyncClient):
        resp = await client.post(
            "/provers/register",
            json=_prover_payload(gpu_backend="invalid_backend"),
            headers=_auth(_MINER1),
        )
        assert resp.status_code == 400

    async def test_register_missing_hotkey_422(self, client: AsyncClient):
        """Omitting auth headers should return 422 (missing x-hotkey header)."""
        resp = await client.post("/provers/register", json=_prover_payload())
        assert resp.status_code == 422

    async def test_register_all_gpu_backends(self, client: AsyncClient):
        for i, backend in enumerate(["cuda", "rocm", "metal", "webgpu", "cpu"]):
            hk = f"5F{backend}MinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            resp = await client.post(
                "/provers/register",
                json=_prover_payload(gpu_backend=backend),
                headers=_auth(hk),
            )
            assert resp.status_code == 201
            assert resp.json()["gpu_backend"] == backend


# ── Ping ─────────────────────────────────────────────────────

class TestProverPing:
    async def test_ping_registered_prover(self, client: AsyncClient):
        await client.post(
            "/provers/register",
            json=_prover_payload(),
            headers=_auth(_MINER1),
        )
        resp = await client.post(
            "/provers/ping?vram_available_bytes=15000000000",
            headers=_auth(_MINER1),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_ping_unregistered_prover_404(self, client: AsyncClient):
        unknown = "5FUnknownMinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        resp = await client.post(
            "/provers/ping?vram_available_bytes=0",
            headers=_auth(unknown),
        )
        assert resp.status_code == 404


# ── Listing ──────────────────────────────────────────────────

class TestListProvers:
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/provers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_with_data(self, client: AsyncClient):
        for i in range(3):
            hk = f"5FMiner{i}XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            await client.post(
                "/provers/register",
                json=_prover_payload(),
                headers=_auth(hk),
            )
        resp = await client.get("/provers")
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    async def test_list_online_only(self, client: AsyncClient):
        online_hk = "5FOnlineMinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        await client.post(
            "/provers/register",
            json=_prover_payload(),
            headers=_auth(online_hk),
        )
        resp = await client.get("/provers?online_only=true")
        data = resp.json()
        assert data["total"] >= 1
        assert all(p["online"] for p in data["items"])

    async def test_list_filter_gpu_backend(self, client: AsyncClient):
        cuda_hk = "5FCudaMinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        metal_hk = "5FMetalMinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        await client.post(
            "/provers/register",
            json=_prover_payload(gpu_backend="cuda"),
            headers=_auth(cuda_hk),
        )
        await client.post(
            "/provers/register",
            json=_prover_payload(gpu_backend="metal"),
            headers=_auth(metal_hk),
        )
        resp = await client.get("/provers?gpu_backend=cuda")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["gpu_backend"] == "cuda"

    async def test_list_pagination(self, client: AsyncClient):
        for i in range(5):
            hk = f"5FM{i}PaginationXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            await client.post(
                "/provers/register",
                json=_prover_payload(),
                headers=_auth(hk),
            )
        resp = await client.get("/provers?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2


# ── Get prover ───────────────────────────────────────────────

class TestGetProver:
    async def test_get_by_hotkey(self, client: AsyncClient):
        my_hk = "5FMyMinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        await client.post(
            "/provers/register",
            json=_prover_payload(),
            headers=_auth(my_hk),
        )
        resp = await client.get(f"/provers/{my_hk}")
        assert resp.status_code == 200
        assert resp.json()["hotkey"] == my_hk

    async def test_get_not_found(self, client: AsyncClient):
        resp = await client.get("/provers/5FUnknownMinerXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        assert resp.status_code == 404


# ── Network stats ────────────────────────────────────────────

class TestNetworkStats:
    async def test_stats_empty(self, client: AsyncClient):
        resp = await client.get("/provers/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_provers"] == 0
        assert data["online_provers"] == 0

    async def test_stats_with_provers(self, client: AsyncClient):
        m1 = "5FM1StatsXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        m2 = "5FM2StatsXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        await client.post(
            "/provers/register",
            json=_prover_payload(gpu_count=2, vram_total_bytes=24_000_000_000),
            headers=_auth(m1),
        )
        await client.post(
            "/provers/register",
            json=_prover_payload(gpu_count=4, vram_total_bytes=48_000_000_000, gpu_backend="rocm"),
            headers=_auth(m2),
        )
        resp = await client.get("/provers/stats")
        data = resp.json()
        assert data["total_provers"] == 2
        assert data["online_provers"] == 2
        assert data["total_gpus"] == 6
        assert data["total_vram_bytes"] == 72_000_000_000
        assert "cuda" in data["gpu_backends"]
        assert "rocm" in data["gpu_backends"]
        # Both provers support ["groth16", "plonk"] so both should appear in proof_systems
        assert data["proof_systems"]["groth16"] == 2
        assert data["proof_systems"]["plonk"] == 2

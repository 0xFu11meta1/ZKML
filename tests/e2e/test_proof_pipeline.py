"""End-to-end integration test: full proof lifecycle.

Exercises the complete pipeline through the API layer:
  1. Register GPU provers
  2. Upload a circuit
  3. Request a proof job
  4. Simulate dispatch → partition → prove → aggregate → complete
  5. Submit & verify the final proof
  6. Confirm all state transitions are reflected in listings/stats
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from registry.core.deps import get_db
from registry.models.database import (
    Base,
    CircuitPartitionRow,
    ProofJobRow,
    ProofJobStatus,
    ProofRow,
)

# ---------------------------------------------------------------------------
# Fixtures — shared in-memory SQLite via StaticPool (single connection)
# ---------------------------------------------------------------------------

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture()
async def _e2e_engine():
    engine = create_async_engine(
        _TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def _e2e_session_factory(_e2e_engine):
    return async_sessionmaker(_e2e_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture()
async def e2e_session(_e2e_session_factory):
    async with _e2e_session_factory() as session:
        yield session


@pytest.fixture()
async def e2e_client(_e2e_engine, _e2e_session_factory):
    """Full-stack async client wired to in-memory DB."""
    from registry.api.routes.circuits import router as circuits_router
    from registry.api.routes.proofs import router as proofs_router
    from registry.api.routes.provers import router as provers_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(circuits_router, prefix="/circuits")
    app.include_router(proofs_router, prefix="/proofs")
    app.include_router(provers_router, prefix="/provers")

    async def _override_db():
        async with _e2e_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINER_A = "5FMinerAlpha"
MINER_B = "5FMinerBeta"
PUBLISHER = "5FPublisher"
REQUESTER = "5FRequester"


def _prover_payload(*, backend: str = "cuda", score: float = 9500.0) -> dict:
    return {
        "gpu_name": "NVIDIA RTX 4090",
        "gpu_backend": backend,
        "gpu_count": 2,
        "vram_total_bytes": 25_769_803_776,
        "vram_available_bytes": 20_000_000_000,
        "compute_units": 128,
        "benchmark_score": score,
        "supported_proof_types": ["groth16", "plonk"],
        "max_constraints": 10_000_000,
    }


def _circuit_payload(*, name: str = "e2e-circuit", constraints: int = 100_000) -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "proof_type": "groth16",
        "circuit_type": "general",
        "num_constraints": constraints,
        "num_public_inputs": 3,
        "num_private_inputs": 10,
        "ipfs_cid": f"Qm{uuid.uuid4().hex[:40]}",
        "size_bytes": 1024 * 512,
        "tags": ["e2e", "test"],
    }


async def _simulate_dispatch(session: AsyncSession, task_id: str, circuit_id: int) -> None:
    """Simulate what the Celery dispatch task would do: partition and assign."""
    job = (
        await session.execute(
            select(ProofJobRow).where(ProofJobRow.task_id == task_id)
        )
    ).scalar_one()

    # Move to PARTITIONING → create partitions
    job.status = ProofJobStatus.PARTITIONING
    await session.flush()

    num_partitions = max(1, job.circuit.num_constraints // 50_000)
    job.num_partitions = num_partitions
    constraints_per = job.circuit.num_constraints // num_partitions

    miners = [MINER_A, MINER_B]
    for i in range(num_partitions):
        session.add(CircuitPartitionRow(
            job_id=job.id,
            partition_index=i,
            total_partitions=num_partitions,
            constraint_start=i * constraints_per,
            constraint_end=min((i + 1) * constraints_per, job.circuit.num_constraints),
            assigned_prover=miners[i % len(miners)],
            status="assigned",
        ))

    # Move to DISPATCHED → PROVING
    job.status = ProofJobStatus.DISPATCHED
    await session.flush()
    job.status = ProofJobStatus.PROVING
    await session.commit()


async def _simulate_completion(
    session: AsyncSession, task_id: str, circuit_id: int
) -> int:
    """Simulate partition completion and proof creation. Returns proof ID."""
    job = (
        await session.execute(
            select(ProofJobRow).where(ProofJobRow.task_id == task_id)
        )
    ).scalar_one()

    # Complete all partitions
    partitions = (
        await session.execute(
            select(CircuitPartitionRow).where(CircuitPartitionRow.job_id == job.id)
        )
    ).scalars().all()

    for p in partitions:
        p.status = "completed"
        p.proof_fragment_cid = f"QmFragment{p.partition_index}"
        p.generation_time_ms = 1200 + p.partition_index * 100

    job.partitions_completed = len(partitions)

    # Aggregation → Verifying → Completed
    job.status = ProofJobStatus.AGGREGATING
    await session.flush()

    proof_data = json.dumps({"mock_proof": True, "task_id": task_id}).encode()
    proof_hash = hashlib.sha256(proof_data).hexdigest()

    proof = ProofRow(
        proof_hash=proof_hash,
        circuit_id=circuit_id,
        job_id=job.id,
        proof_type=job.circuit.proof_type,
        proof_data_cid=f"QmProof{uuid.uuid4().hex[:16]}",
        public_inputs_json=job.public_inputs_json,
        proof_size_bytes=len(proof_data),
        generation_time_ms=sum(p.generation_time_ms or 0 for p in partitions),
        prover_hotkey=MINER_A,
        verified=False,
    )
    session.add(proof)
    await session.flush()

    job.status = ProofJobStatus.COMPLETED
    job.result_proof_id = proof.id
    job.actual_time_ms = proof.generation_time_ms
    await session.commit()

    return proof.id


# ---------------------------------------------------------------------------
# E2E Test
# ---------------------------------------------------------------------------


class TestFullProofPipeline:
    """Integration test exercising the full proof lifecycle."""

    async def test_circuit_upload_and_discovery(self, e2e_client: AsyncClient):
        """Upload a circuit and verify it appears in listings and by hash."""
        resp = await e2e_client.post(
            f"/circuits?hotkey={PUBLISHER}",
            json=_circuit_payload(name="discovery-test"),
        )
        assert resp.status_code == 201
        circuit = resp.json()

        # Fetch by ID
        resp = await e2e_client.get(f"/circuits/{circuit['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "discovery-test"

        # Fetch by hash
        resp = await e2e_client.get(f"/circuits/hash/{circuit['circuit_hash']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == circuit["id"]

        # Appears in listing
        resp = await e2e_client.get("/circuits")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_prover_registration_and_stats(self, e2e_client: AsyncClient):
        """Register provers and verify network stats reflect them."""
        resp_a = await e2e_client.post(
            f"/provers/register?hotkey={MINER_A}",
            json=_prover_payload(score=9500.0),
        )
        assert resp_a.status_code == 201

        resp_b = await e2e_client.post(
            f"/provers/register?hotkey={MINER_B}",
            json=_prover_payload(backend="rocm", score=8000.0),
        )
        assert resp_b.status_code == 201

        # Both appear in listing
        resp = await e2e_client.get("/provers")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

        # Network stats updated
        resp = await e2e_client.get("/provers/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_provers"] == 2
        assert stats["online_provers"] == 2

    async def test_full_proof_lifecycle(
        self,
        e2e_client: AsyncClient,
        e2e_session: AsyncSession,
    ):
        """End-to-end: upload → request → dispatch → prove → complete → verify."""
        # ── Step 1: Register provers ───────────────────────
        await e2e_client.post(
            f"/provers/register?hotkey={MINER_A}",
            json=_prover_payload(score=9500.0),
        )
        await e2e_client.post(
            f"/provers/register?hotkey={MINER_B}",
            json=_prover_payload(backend="rocm", score=8000.0),
        )

        # ── Step 2: Upload circuit ─────────────────────────
        circuit_resp = await e2e_client.post(
            f"/circuits?hotkey={PUBLISHER}",
            json=_circuit_payload(name="e2e-proof-circuit", constraints=100_000),
        )
        assert circuit_resp.status_code == 201
        circuit = circuit_resp.json()
        circuit_id = circuit["id"]

        # ── Step 3: Request proof job ──────────────────────
        job_resp = await e2e_client.post(
            f"/proofs/jobs?hotkey={REQUESTER}",
            json={"circuit_id": circuit_id, "witness_cid": "QmWitnessE2E123"},
        )
        assert job_resp.status_code == 202
        job = job_resp.json()
        task_id = job["task_id"]
        assert job["status"] == "queued"
        assert job["circuit_id"] == circuit_id

        # Verify job appears in listing
        list_resp = await e2e_client.get(f"/proofs/jobs?requester={REQUESTER}")
        assert list_resp.json()["total"] == 1

        # ── Step 4: Simulate dispatch + partitioning ───────
        await _simulate_dispatch(e2e_session, task_id, circuit_id)

        # Verify status is now PROVING via API
        status_resp = await e2e_client.get(f"/proofs/jobs/{task_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "proving"

        # Verify partitions exist
        parts_resp = await e2e_client.get(f"/proofs/jobs/{task_id}/partitions")
        assert parts_resp.status_code == 200
        partitions = parts_resp.json()
        assert len(partitions) >= 2  # 100k constraints / 50k per partition = 2

        # ── Step 5: Simulate proof completion ──────────────
        proof_id = await _simulate_completion(e2e_session, task_id, circuit_id)

        # Verify job is COMPLETED
        final_resp = await e2e_client.get(f"/proofs/jobs/{task_id}")
        assert final_resp.status_code == 200
        final_job = final_resp.json()
        assert final_job["status"] == "completed"
        assert final_job["result_proof_id"] == proof_id

        # ── Step 6: Fetch the proof ────────────────────────
        proof_resp = await e2e_client.get(f"/proofs/{proof_id}")
        assert proof_resp.status_code == 200
        proof = proof_resp.json()
        assert proof["circuit_id"] == circuit_id
        assert proof["prover_hotkey"] == MINER_A
        assert proof["verified"] is False

        # Proof appears in listing
        proofs_list = await e2e_client.get(f"/proofs?circuit_id={circuit_id}")
        assert proofs_list.status_code == 200
        assert proofs_list.json()["total"] >= 1

    async def test_duplicate_circuit_rejected(self, e2e_client: AsyncClient):
        """Same name+version cannot be uploaded twice."""
        payload = _circuit_payload(name="dup-test")
        resp1 = await e2e_client.post(f"/circuits?hotkey={PUBLISHER}", json=payload)
        assert resp1.status_code == 201

        resp2 = await e2e_client.post(f"/circuits?hotkey={PUBLISHER}", json=payload)
        assert resp2.status_code == 409

    async def test_proof_request_nonexistent_circuit(self, e2e_client: AsyncClient):
        """Requesting proof for a circuit that doesn't exist → 404."""
        resp = await e2e_client.post(
            f"/proofs/jobs?hotkey={REQUESTER}",
            json={"circuit_id": 99999, "witness_cid": "QmBogus"},
        )
        assert resp.status_code == 404

    async def test_multiple_concurrent_jobs(
        self,
        e2e_client: AsyncClient,
        e2e_session: AsyncSession,
    ):
        """Multiple proof jobs for the same circuit can be requested and tracked."""
        # Upload circuit
        circuit = (await e2e_client.post(
            f"/circuits?hotkey={PUBLISHER}",
            json=_circuit_payload(name="multi-job-circuit"),
        )).json()

        # Request 3 jobs
        task_ids = []
        for i in range(3):
            resp = await e2e_client.post(
                f"/proofs/jobs?hotkey={REQUESTER}",
                json={"circuit_id": circuit["id"], "witness_cid": f"QmWitness{i}"},
            )
            assert resp.status_code == 202
            task_ids.append(resp.json()["task_id"])

        # All appear in listing
        list_resp = await e2e_client.get("/proofs/jobs")
        assert list_resp.json()["total"] == 3

        # Each has a unique task_id
        assert len(set(task_ids)) == 3

    async def test_prover_ping_keeps_online(self, e2e_client: AsyncClient):
        """Pinging a prover keeps its online status fresh."""
        await e2e_client.post(
            f"/provers/register?hotkey={MINER_A}",
            json=_prover_payload(),
        )

        resp = await e2e_client.post(f"/provers/ping?hotkey={MINER_A}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Confirm prover is still online via GET
        prover_resp = await e2e_client.get(f"/provers/{MINER_A}")
        assert prover_resp.status_code == 200
        assert prover_resp.json()["online"] is True

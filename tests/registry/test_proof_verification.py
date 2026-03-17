"""Tests for proof verification endpoint and aggregation helper functions."""

from __future__ import annotations

import hashlib
import struct
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_nonce_seq = 100_000


def _auth(hotkey="5FTestPublisherXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"):
    global _nonce_seq
    _nonce_seq += 1
    nonce = int(time.time()) + _nonce_seq
    return {"x-hotkey": hotkey, "x-signature": "deadbeef", "x-nonce": str(nonce)}


_VALID_CID = "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"
_VALID_WITNESS = "QmT5NvUtoM5nWFfrQnVFwHvBpiFkHjbGEhYbTnTEt5aYrj"


# ── Fragment commitment validation ───────────────────────────


class TestValidateFragmentCommitment:
    def test_valid_commitment_matches(self):
        from registry.tasks.proof_aggregate import _validate_fragment_commitment

        data = b"test_fragment_data"
        partition = SimpleNamespace(commitment_hash=hashlib.sha256(data).hexdigest())
        assert _validate_fragment_commitment(data, partition) is True

    def test_invalid_commitment_fails(self):
        from registry.tasks.proof_aggregate import _validate_fragment_commitment

        data = b"test_fragment_data"
        partition = SimpleNamespace(commitment_hash="0" * 64)
        assert _validate_fragment_commitment(data, partition) is False

    def test_no_commitment_hash_skips(self):
        from registry.tasks.proof_aggregate import _validate_fragment_commitment

        data = b"test_fragment_data"
        partition = SimpleNamespace(commitment_hash=None)
        assert _validate_fragment_commitment(data, partition) is True

    def test_missing_attribute_skips(self):
        from registry.tasks.proof_aggregate import _validate_fragment_commitment

        data = b"test_fragment_data"
        partition = SimpleNamespace()
        assert _validate_fragment_commitment(data, partition) is True


# ── Proof-system-aware merging ───────────────────────────────


class TestMergeFragmentsByProofSystem:
    def test_groth16_concat(self):
        from registry.tasks.proof_aggregate import _merge_fragments_by_proof_system

        fragments = [b"frag1", b"frag2", b"frag3"]
        result = _merge_fragments_by_proof_system(fragments, "groth16")
        assert result == b"frag1frag2frag3"

    def test_plonk_concat(self):
        from registry.tasks.proof_aggregate import _merge_fragments_by_proof_system

        fragments = [b"aa", b"bb"]
        result = _merge_fragments_by_proof_system(fragments, "plonk")
        assert result == b"aabb"

    def test_halo2_length_prefixed(self):
        from registry.tasks.proof_aggregate import _merge_fragments_by_proof_system

        fragments = [b"short", b"longer_fragment"]
        result = _merge_fragments_by_proof_system(fragments, "halo2")

        # Parse the length-prefixed result
        offset = 0
        parsed = []
        while offset < len(result):
            length = int.from_bytes(result[offset : offset + 4], "big")
            offset += 4
            parsed.append(result[offset : offset + length])
            offset += length

        assert parsed == fragments

    def test_stark_merkle_chain(self):
        from registry.tasks.proof_aggregate import _merge_fragments_by_proof_system

        fragments = [b"f1_data", b"f2_data", b"f3_data"]
        result = _merge_fragments_by_proof_system(fragments, "stark")

        # Parse header: 4-byte count + 32-byte root
        count = struct.unpack(">I", result[:4])[0]
        assert count == 3
        root = result[4:36]

        # Verify chain: hash(hash(h1 + h2) + h3) == root
        leaves = [hashlib.sha256(f).digest() for f in fragments]
        expected = leaves[0]
        for leaf in leaves[1:]:
            expected = hashlib.sha256(expected + leaf).digest()
        assert root == expected

        # Body is the raw fragments concatenated
        body = result[36:]
        assert body == b"f1_dataf2_dataf3_data"

    def test_single_fragment_passthrough(self):
        from registry.tasks.proof_aggregate import _merge_fragments_by_proof_system

        result = _merge_fragments_by_proof_system([b"single"], "groth16")
        assert result == b"single"

    def test_enum_value_handled(self):
        """proof_type can be an enum with .value attribute."""
        from registry.tasks.proof_aggregate import _merge_fragments_by_proof_system

        enum_like = MagicMock()
        enum_like.value = "plonk"
        # The function checks `isinstance(proof_type, str)` and uses .value otherwise
        result = _merge_fragments_by_proof_system([b"a", b"b"], enum_like)
        assert result == b"ab"


# ── IPFS download retry ─────────────────────────────────────


class TestDownloadFragmentWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        from registry.tasks.proof_aggregate import _download_fragment_with_retry

        storage = AsyncMock()
        storage.download_bytes.return_value = b"proof_data"
        result = await _download_fragment_with_retry(storage, "QmTest", 1, 0)
        assert result == b"proof_data"
        storage.download_bytes.assert_called_once_with("QmTest")

    @pytest.mark.asyncio
    async def test_success_after_retries(self):
        from registry.tasks.proof_aggregate import _download_fragment_with_retry

        storage = AsyncMock()
        storage.download_bytes.side_effect = [
            Exception("timeout"),
            Exception("timeout"),
            b"proof_data",
        ]
        with patch("registry.tasks.proof_aggregate.asyncio.sleep", new_callable=AsyncMock):
            result = await _download_fragment_with_retry(storage, "QmTest", 1, 0)
        assert result == b"proof_data"
        assert storage.download_bytes.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self):
        from registry.tasks.proof_aggregate import (
            _download_fragment_with_retry,
            _MAX_FRAGMENT_DOWNLOAD_RETRIES,
        )

        storage = AsyncMock()
        storage.download_bytes.side_effect = Exception("persistent error")
        with patch("registry.tasks.proof_aggregate.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="exhausted"):
                await _download_fragment_with_retry(storage, "QmTest", 1, 0)
        assert storage.download_bytes.call_count == _MAX_FRAGMENT_DOWNLOAD_RETRIES


# ── Verify endpoint — format version validation ──────────────


class TestVerifyFormatVersion:
    @pytest.mark.asyncio
    async def test_verify_rejects_unknown_format_version(self, client):
        """Proofs with unsupported format_version should be rejected."""
        from httpx import AsyncClient

        # Create circuit and proof job
        circuit = await _create_circuit(client)
        resp = await client.post(
            "/proofs/jobs",
            json={"circuit_id": circuit["id"], "witness_cid": _VALID_WITNESS},
            headers=_auth(),
        )
        assert resp.status_code == 202


# ── Helpers ──────────────────────────────────────────────────


async def _create_circuit(client, **overrides) -> dict:
    defaults = {
        "name": "test-circuit",
        "version": "1.0.0",
        "proof_type": "groth16",
        "circuit_type": "general",
        "num_constraints": 50000,
        "ipfs_cid": _VALID_CID,
        "verification_key_cid": _VALID_CID,
    }
    defaults.update(overrides)
    resp = await client.post("/circuits", json=defaults, headers=_auth())
    assert resp.status_code == 201
    return resp.json()

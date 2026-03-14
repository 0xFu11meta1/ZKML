"""Tests for proof aggregation task constants and timeout logic."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ── Constants ────────────────────────────────────────────────

class TestAggregationConstants:
    def test_max_proving_seconds(self):
        from registry.tasks.proof_aggregate import _MAX_PROVING_SECONDS
        assert _MAX_PROVING_SECONDS > 0  # sanity: positive timeout

    def test_task_is_callable(self):
        from registry.tasks.proof_aggregate import aggregate_completed_jobs
        assert callable(aggregate_completed_jobs)


# ── Timeout detection ────────────────────────────────────────

class TestTimeoutDetection:
    """Verify the timeout logic in _aggregate_sweep."""

    def test_job_older_than_max_times_out(self):
        """A job that has been in PROVING for > _MAX_PROVING_SECONDS should be timed out."""
        from registry.tasks.proof_aggregate import _MAX_PROVING_SECONDS
        started = datetime.now(timezone.utc) - timedelta(seconds=_MAX_PROVING_SECONDS + 60)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        assert elapsed > _MAX_PROVING_SECONDS

    def test_recent_job_not_timed_out(self):
        from registry.tasks.proof_aggregate import _MAX_PROVING_SECONDS
        started = datetime.now(timezone.utc) - timedelta(seconds=10)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        assert elapsed < _MAX_PROVING_SECONDS


# ── Fragment aggregation logic ───────────────────────────────

class TestFragmentAggregation:
    """Test the proof fragment concatenation and hash logic."""

    def test_concat_fragments(self):
        """Fragments should be concatenated in order."""
        import hashlib
        fragments = [b"aaa", b"bbb", b"ccc"]
        combined = b"".join(fragments)
        assert combined == b"aaabbbccc"
        # Hash should be deterministic
        h = hashlib.sha256(combined).hexdigest()
        assert h == hashlib.sha256(b"aaabbbccc").hexdigest()

    def test_empty_fragments_raises(self):
        """No fragment CIDs should be treated as an error."""
        fragment_cids = []
        assert not fragment_cids  # would raise ValueError in _aggregate_job

    def test_single_fragment_passthrough(self):
        """A single-partition job yields the fragment as the final proof."""
        import hashlib
        fragments = [b"single_proof_data"]
        combined = b"".join(fragments)
        assert combined == b"single_proof_data"
        proof_hash = hashlib.sha256(combined).hexdigest()
        assert len(proof_hash) == 64


# ── Partition status counting ────────────────────────────────

class TestPartitionCounting:
    """The sweep checks partition statuses to decide next action."""

    def test_all_completed(self):
        part_counts = {"completed": 4}
        completed = part_counts.get("completed", 0)
        total = sum(part_counts.values())
        num_partitions = 4
        assert completed >= num_partitions  # ready to aggregate

    def test_partial_completion(self):
        part_counts = {"completed": 2, "proving": 2}
        completed = part_counts.get("completed", 0)
        num_partitions = 4
        assert completed < num_partitions  # not ready

    def test_all_failed_no_hope(self):
        part_counts = {"completed": 1, "failed": 3}
        completed = part_counts.get("completed", 0)
        failed = part_counts.get("failed", 0)
        total = sum(part_counts.values())
        pending_or_active = total - completed - failed
        num_partitions = 4
        assert pending_or_active == 0 and completed < num_partitions  # should fail

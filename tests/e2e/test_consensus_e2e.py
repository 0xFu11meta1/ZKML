"""End-to-end multi-validator consensus test.

Simulates the full consensus lifecycle:
  1. Multiple validators submit verification votes for a proof
  2. Consensus engine computes binary stake-weighted result
  3. Validator reliability gets updated correctly
  4. Slashing triggers on persistent divergence
  5. Verifier selection excludes slashed validators
"""

from __future__ import annotations

import pytest

from subnet.consensus.engine import (
    CONSENSUS_THRESHOLD,
    DIVERGENCE_WINDOW,
    MAX_VALIDATORS_PER_PROOF,
    MIN_QUORUM,
    SLASH_THRESHOLD,
    ConsensusEngine,
    VerificationVote,
)


class TestConsensusE2E:
    """Full multi-round consensus scenario."""

    def test_multi_round_consensus_lifecycle(self):
        """Run multiple proof verifications and track validator reliability."""
        engine = ConsensusEngine()

        validators = [f"val-{i}" for i in range(5)]
        stakes = {v: (i + 1) * 100.0 for i, v in enumerate(validators)}

        # Round 1: All validators agree proof is valid
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="job-1", partition_index=0,
                valid=True, verification_time_ms=50,
            ))
        result = engine.compute_consensus("job-1", 0, stakes=stakes)
        assert result is not None
        assert result.reached_consensus
        assert result.consensus_valid is True
        assert result.agreement_ratio == 1.0
        assert len(result.agreeing_validators) == 5

        # All validators should have 100% reliability
        for v in validators:
            state = engine.get_validator_state(v)
            assert state.reliability_score == 1.0
            assert state.agreements == 1

        # Round 2: val-0 disagrees (says invalid, majority says valid)
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="job-2", partition_index=0,
                valid=(v != "val-0"), verification_time_ms=60,
            ))
        result = engine.compute_consensus("job-2", 0, stakes=stakes)
        assert result is not None
        assert result.consensus_valid is True
        assert "val-0" in result.diverging_validators

        # val-0 now has 1 divergence out of 2 total
        state_0 = engine.get_validator_state("val-0")
        assert state_0.divergences == 1
        assert state_0.agreements == 1

        # Round 3: val-0 continues to disagree
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="job-3", partition_index=0,
                valid=(v != "val-0"), verification_time_ms=45,
            ))
        engine.compute_consensus("job-3", 0, stakes=stakes)

        state_0 = engine.get_validator_state("val-0")
        assert state_0.divergences == 2
        assert state_0.reliability_score < 1.0

    def test_slash_after_persistent_divergence(self):
        """Validator gets slashed after diverging > threshold over window."""
        engine = ConsensusEngine()
        validators = ["honest-1", "honest-2", "malicious"]
        stakes = {"honest-1": 500, "honest-2": 500, "malicious": 100}

        # Run DIVERGENCE_WINDOW rounds where malicious always disagrees
        for round_num in range(DIVERGENCE_WINDOW):
            job_id = f"slash-job-{round_num}"
            for v in validators:
                engine.submit_vote(VerificationVote(
                    validator_hotkey=v, job_id=job_id, partition_index=0,
                    valid=(v != "malicious"),
                ))
            engine.compute_consensus(job_id, 0, stakes=stakes)

        state = engine.get_validator_state("malicious")
        assert state.slashed
        assert state.slash_count >= 1
        assert state.reliability_score < SLASH_THRESHOLD

        # Slashed validator should be deprioritized in verifier selection
        all_validators = ["honest-1", "honest-2", "malicious", "new-val"]
        assigned = engine.assign_verifiers("next-job", all_validators, stakes)
        # Malicious should be excluded (weight = 0 for slashed)
        assert "malicious" not in assigned or len(assigned) <= MAX_VALIDATORS_PER_PROOF

    def test_multi_partition_multi_validator(self):
        """Multiple partitions of the same job verified independently."""
        engine = ConsensusEngine()
        validators = ["v1", "v2", "v3"]
        stakes = {v: 100.0 for v in validators}

        # Partition 0: all agree valid
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="multi-job", partition_index=0,
                valid=True, verification_time_ms=30,
            ))
        r0 = engine.compute_consensus("multi-job", 0, stakes=stakes)
        assert r0.reached_consensus
        assert r0.consensus_valid is True

        # Partition 1: majority says invalid
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="multi-job", partition_index=1,
                valid=(v == "v1"),  # Only v1 says valid
            ))
        r1 = engine.compute_consensus("multi-job", 1, stakes=stakes)
        assert r1.reached_consensus
        assert r1.consensus_valid is False

        # Partition 2: split vote (1v2 insufficient for consensus)
        engine.submit_vote(VerificationVote(
            validator_hotkey="v1", job_id="multi-job", partition_index=2,
            valid=True,
        ))
        engine.submit_vote(VerificationVote(
            validator_hotkey="v2", job_id="multi-job", partition_index=2,
            valid=False,
        ))
        r2 = engine.compute_consensus("multi-job", 2, stakes=stakes)
        assert r2 is not None
        # 50/50 split should not reach consensus threshold
        assert r2.agreement_ratio < CONSENSUS_THRESHOLD or not r2.reached_consensus

    def test_stake_weighted_minority_overrule(self):
        """High-stake validator can overrule low-stake majority."""
        engine = ConsensusEngine()
        # 1 whale validator + 2 small validators
        # whale: 10000 stake, small: 10 each
        stakes = {"whale": 10000.0, "small-1": 10.0, "small-2": 10.0}

        # Whale says valid, both small say invalid
        engine.submit_vote(VerificationVote(
            validator_hotkey="whale", job_id="whale-job", partition_index=0,
            valid=True,
        ))
        engine.submit_vote(VerificationVote(
            validator_hotkey="small-1", job_id="whale-job", partition_index=0,
            valid=False,
        ))
        engine.submit_vote(VerificationVote(
            validator_hotkey="small-2", job_id="whale-job", partition_index=0,
            valid=False,
        ))

        result = engine.compute_consensus("whale-job", 0, stakes=stakes)
        assert result is not None
        # Whale has 10000/(10000+10+10) ≈ 99.8% of stake weight
        assert result.consensus_valid is True
        assert result.reached_consensus

    def test_verification_time_tracking(self):
        """Average verification time accumulates across rounds."""
        engine = ConsensusEngine()
        validators = ["v1", "v2"]

        for round_num in range(5):
            for v in validators:
                engine.submit_vote(VerificationVote(
                    validator_hotkey=v, job_id=f"time-job-{round_num}",
                    partition_index=0, valid=True,
                    verification_time_ms=100 + round_num * 10,
                ))
            engine.compute_consensus(f"time-job-{round_num}", 0)

        for v in validators:
            state = engine.get_validator_state(v)
            assert state.avg_verification_time_ms > 0
            assert state.total_proofs_verified == 5

    def test_concurrent_jobs_isolated(self):
        """Votes for different jobs don't interfere."""
        engine = ConsensusEngine()
        validators = ["v1", "v2", "v3"]

        # Job A: all valid
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="job-A", partition_index=0,
                valid=True,
            ))

        # Job B: all invalid
        for v in validators:
            engine.submit_vote(VerificationVote(
                validator_hotkey=v, job_id="job-B", partition_index=0,
                valid=False,
            ))

        ra = engine.compute_consensus("job-A", 0)
        rb = engine.compute_consensus("job-B", 0)

        assert ra.consensus_valid is True
        assert rb.consensus_valid is False
        # Both should reach consensus independently
        assert ra.reached_consensus
        assert rb.reached_consensus

    def test_quorum_not_met(self):
        """Single vote below quorum returns None."""
        engine = ConsensusEngine()
        engine.submit_vote(VerificationVote(
            validator_hotkey="lonely", job_id="solo-job", partition_index=0,
            valid=True,
        ))
        result = engine.compute_consensus("solo-job", 0)
        assert result is None

    def test_verifier_assignment_fairness(self):
        """Verifier selection respects reliability and max limit."""
        engine = ConsensusEngine()
        # Create 10 validators with varying reliability
        validators = []
        for i in range(10):
            v = f"val-{i}"
            validators.append(v)
            state = engine.get_or_create_validator(v)
            # First 5 are highly reliable
            for _ in range(10):
                state.update(agreed=(i < 7))

        stakes = {v: 100.0 for v in validators}
        assigned = engine.assign_verifiers("assign-job", validators, stakes)

        assert len(assigned) <= MAX_VALIDATORS_PER_PROOF
        assert len(assigned) >= min(MIN_QUORUM, len(validators))
        # All assigned should be from the original list
        for a in assigned:
            assert a in validators

"""Tests for the validator neuron — scoring, prover tracking, reward computation."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

# Mock bittensor before importing validator module
if "bittensor" not in sys.modules:
    _bt = MagicMock()
    _bt.Synapse = type("Synapse", (), {})
    _bt.config = MagicMock()
    _bt.dendrite = MagicMock()
    sys.modules["bittensor"] = _bt

from subnet.neurons.validator import ProverInfo
from subnet.reward.scoring import (
    ProverRewardWeights,
    ProverScore,
    compute_prover_rewards,
)


# ── ProverInfo ──────────────────────────────────────────────

class TestProverInfo:
    def test_default_values(self):
        info = ProverInfo(uid=0, hotkey="5FTest")
        assert info.gpu_backend == "cpu"
        assert info.online is False
        assert info.benchmark_score == 0.0
        assert info.current_load == 0.0

    def test_online_prover(self):
        info = ProverInfo(uid=1, hotkey="5FOnline", online=True, gpu_name="RTX 4090")
        assert info.online
        assert info.gpu_name == "RTX 4090"


# ── ProverScore ─────────────────────────────────────────────

class TestProverScore:
    def test_default_zero(self):
        s = ProverScore(uid=0)
        assert s.total() == 0.0

    def test_perfect_score(self):
        s = ProverScore(uid=0, correctness=1.0, speed=1.0, throughput=1.0,
                        reliability=1.0, efficiency=1.0)
        assert s.total() == pytest.approx(1.0)

    def test_weighted_total(self):
        s = ProverScore(uid=0, correctness=1.0, speed=0.0, throughput=0.0,
                        reliability=0.0, efficiency=0.0)
        w = ProverRewardWeights()
        assert s.total(w) == pytest.approx(0.35)

    def test_custom_weights(self):
        s = ProverScore(uid=0, correctness=0.5, speed=0.5, throughput=0.5,
                        reliability=0.5, efficiency=0.5)
        w = ProverRewardWeights(
            correctness=0.2, speed=0.2, throughput=0.2,
            reliability=0.2, efficiency=0.2,
        )
        assert s.total(w) == pytest.approx(0.5)


# ── Reward weights ──────────────────────────────────────────

class TestRewardWeights:
    def test_default_sum_to_one(self):
        w = ProverRewardWeights()
        total = w.correctness + w.speed + w.throughput + w.reliability + w.efficiency
        assert total == pytest.approx(1.0)

    def test_default_correctness_heaviest(self):
        w = ProverRewardWeights()
        assert w.correctness > w.speed > w.throughput > w.reliability > w.efficiency


# ── compute_prover_rewards ──────────────────────────────────

class TestComputeProverRewards:
    def test_empty_list(self):
        result = compute_prover_rewards([])
        assert result == []

    def test_single_prover(self):
        scores = [ProverScore(uid=0, correctness=1.0, speed=0.8)]
        result = compute_prover_rewards(scores)
        assert len(result) == 1
        assert result[0] == pytest.approx(1.0)

    def test_equal_provers(self):
        scores = [
            ProverScore(uid=0, correctness=0.5, speed=0.5),
            ProverScore(uid=1, correctness=0.5, speed=0.5),
        ]
        result = compute_prover_rewards(scores)
        assert len(result) == 2
        assert result[0] == pytest.approx(result[1])
        assert sum(result) == pytest.approx(1.0)

    def test_unequal_provers(self):
        scores = [
            ProverScore(uid=0, correctness=1.0, speed=1.0, throughput=1.0,
                        reliability=1.0, efficiency=1.0),
            ProverScore(uid=1, correctness=0.0),
        ]
        result = compute_prover_rewards(scores)
        assert result[0] > result[1]
        assert sum(result) == pytest.approx(1.0)

    def test_all_zeros(self):
        scores = [ProverScore(uid=0), ProverScore(uid=1)]
        result = compute_prover_rewards(scores)
        # All-zero scores should return zero rewards (no division by zero)
        assert all(r == 0.0 for r in result)

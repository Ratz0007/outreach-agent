"""Tests for A/B testing engine statistical rules."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.testing.ab_engine import evaluate_variants, apply_recommendations, get_variant_performance
from src.config import AgentConfig


def test_no_evaluation_before_threshold():
    """Should not evaluate until 30+ total replies."""
    result = evaluate_variants()
    # With seed data we have < 30 replies
    assert result["can_evaluate"] is False, "Should not evaluate with <30 replies"
    assert result["kill"] == []
    assert result["boost"] == []
    print("PASS: test_no_evaluation_before_threshold")


def test_get_variant_performance():
    """Should return stats for all 10 variants."""
    stats = get_variant_performance()
    assert len(stats) == 10, f"Expected 10 variants, got {len(stats)}"
    for s in stats:
        assert s.variant_id.startswith("V")
        assert s.style in ("referral", "value_first", "conversational")
        assert 0 <= s.reply_rate <= 100
    print("PASS: test_get_variant_performance")


def test_apply_recommendations_normalize():
    """Weights should normalize to ~1.0 after applying recommendations."""
    # Simulate a kill recommendation
    recs = {"kill": ["V6"], "boost": ["V1"], "active_count": 10}
    updated = apply_recommendations(recs)
    active_weights = sum(v["weight"] for v in updated.values() if v.get("active", True))
    assert 0.95 <= active_weights <= 1.05, f"Weights sum to {active_weights} after normalization"
    assert updated["V6"]["active"] is False
    print("PASS: test_apply_recommendations_normalize")


def test_min_active_variants_enforced():
    """Should never kill below 4 active variants."""
    # With only 1 send and 0 replies, nothing should be killed
    result = evaluate_variants()
    remaining = result["active_count"] - len(result["kill"])
    assert remaining >= AgentConfig.min_active_variants
    print("PASS: test_min_active_variants_enforced")


if __name__ == "__main__":
    test_no_evaluation_before_threshold()
    test_get_variant_performance()
    test_apply_recommendations_normalize()
    test_min_active_variants_enforced()
    print("\n=== ALL A/B ENGINE TESTS PASSED ===")

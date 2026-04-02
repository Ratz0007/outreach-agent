"""Tests for message generation and variant system."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.messaging.variants import (
    VARIANT_TEMPLATES, get_variant_template, get_variants_by_style, get_all_active_variant_ids
)
from src.config import AgentConfig


def test_all_10_variants_defined():
    """Verify all 10 variants exist with required fields."""
    for i in range(1, 11):
        vid = f"V{i}"
        v = VARIANT_TEMPLATES.get(vid)
        assert v is not None, f"{vid} missing"
        assert "style" in v, f"{vid} missing style"
        assert "template" in v, f"{vid} missing template"
        assert v["style"] in ("referral", "value_first", "conversational")
    print("PASS: test_all_10_variants_defined")


def test_variant_styles():
    """Verify style groupings."""
    referral = get_variants_by_style("referral")
    value_first = get_variants_by_style("value_first")
    conversational = get_variants_by_style("conversational")

    assert set(referral) == {"V1", "V2", "V3"}, f"Referral variants wrong: {referral}"
    assert set(value_first) == {"V4", "V5", "V6"}, f"Value-first variants wrong: {value_first}"
    assert set(conversational) == {"V7", "V8", "V9", "V10"}, f"Conversational variants wrong: {conversational}"
    print("PASS: test_variant_styles")


def test_variant_templates_have_tokens():
    """Verify templates use personalisation tokens."""
    for vid, v in VARIANT_TEMPLATES.items():
        template = v["template"]
        # Every template should have at least {Company} or {Name}
        has_token = "{Name}" in template or "{Company}" in template
        assert has_token, f"{vid} template has no personalisation tokens"
    print("PASS: test_variant_templates_have_tokens")


def test_config_weights_sum_to_1():
    """Config variant weights should roughly sum to 1."""
    total = sum(v.get("weight", 0) for v in AgentConfig.variants.values())
    assert 0.95 <= total <= 1.05, f"Weights sum to {total}, expected ~1.0"
    print("PASS: test_config_weights_sum_to_1")


def test_active_variants():
    """All variants should be active by default."""
    active = get_all_active_variant_ids(AgentConfig.variants)
    assert len(active) == 10, f"Expected 10 active variants, got {len(active)}"
    print("PASS: test_active_variants")


if __name__ == "__main__":
    test_all_10_variants_defined()
    test_variant_styles()
    test_variant_templates_have_tokens()
    test_config_weights_sum_to_1()
    test_active_variants()
    print("\n=== ALL MESSAGING TESTS PASSED ===")

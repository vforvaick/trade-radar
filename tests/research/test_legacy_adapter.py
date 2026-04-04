"""Tests for legacy v1-to-v2 passport adapter."""
import os
import pytest


def test_convert_v1():
    from bot.research.legacy_adapter import convert_v1_to_v2
    v1 = {
        "name": "Pumpradar OG",
        "version": "0.1",
        "indicator_weights": {"ema_trend": 1.0},
        "confidence_threshold": 54,
    }
    v2 = convert_v1_to_v2(v1)
    assert v2["schema_version"] == 2
    assert v2["lineage"]["lineage_type"] == "migration"
    assert v2["family"] == "balanced_all"


def test_scan_and_convert():
    from bot.research.legacy_adapter import scan_and_convert
    d = "pumpradar-passports/configs"
    if not os.path.exists(d):
        pytest.skip("No legacy passports")
    results = scan_and_convert(d)
    assert len(results) > 0
    assert all(r["schema_version"] == 2 for r in results)

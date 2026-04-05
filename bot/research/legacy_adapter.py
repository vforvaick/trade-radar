"""Legacy v1-to-v2 passport adapter.

Converts existing passport JSON files to the v2 schema format used by
the Strategy Research Engine's PassportRegistry.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from bot.research.generator import generate_passport_id


# Map legacy passport names to research family names
FAMILY_MAP: dict[str, str] = {
    "Pumpradar OG": "balanced_all",
    "og": "balanced_all",
    "og_original": "balanced_all",
    "Pumpradar HiddenGem": "hidden_gem_variant",
    "hidden_gem": "hidden_gem_variant",
    "Pumpradar Momentum": "momentum_heavy",
    "momentum": "momentum_heavy",
    "Pumpradar Dynamic": "momentum_heavy",
    "dynamic_exit": "momentum_heavy",
    "Pumpradar Reversal": "rsi_bb_reversal",
    "reversal": "rsi_bb_reversal",
    "Pumpradar Sniper": "sniper_variant",
    "sniper": "sniper_variant",
    "Pumpradar VolumeKing": "volume_spike_breakout",
    "volume_king": "volume_spike_breakout",
}


def convert_v1_to_v2(v1_config: dict) -> dict:
    """Convert a v1 passport config dict to v2 schema.

    Args:
        v1_config: dict with keys like name, version, indicator_weights, etc.

    Returns:
        v2 passport dict with schema_version=2 and lineage info
    """
    name = v1_config.get("name", "unknown")
    version = v1_config.get("version", "0.1")
    family = FAMILY_MAP.get(name, FAMILY_MAP.get(
        name.lower().replace("pumpradar ", ""), "unknown",
    ))

    # Extract config overrides from v1
    config_overrides = {}
    if "indicator_weights" in v1_config:
        config_overrides["INDICATOR_WEIGHTS"] = v1_config["indicator_weights"]
    if "confidence_threshold" in v1_config:
        config_overrides["CONFIDENCE_THRESHOLD"] = v1_config["confidence_threshold"]

    # Copy other numeric params
    for key in ["VOLUME_SPIKE_THRESHOLD", "RSI_PERIOD", "BB_PERIOD", "BB_STD",
                "EMA_FAST", "EMA_MID", "EMA_SLOW"]:
        if key in v1_config:
            config_overrides[key] = v1_config[key]
        elif key.lower() in v1_config:
            config_overrides[key] = v1_config[key.lower()]

    return {
        "schema_version": 2,
        "passport_id": generate_passport_id(),
        "slug": name.lower().replace(" ", "-"),
        "family": family,
        "version": version,
        "config": config_overrides,
        "lineage": {
            "parent_passport_id": None,
            "root_passport_id": None,
            "lineage_type": "migration",
        },
        "created_at": time.time(),
        "migrated_from": name,
    }


def scan_and_convert(passport_dir: str) -> list[dict]:
    """Scan a directory of v1 passport JSON files and convert all to v2.

    Args:
        passport_dir: path to directory containing *.json passport configs

    Returns:
        list of v2 passport dicts
    """
    results = []
    for fname in sorted(os.listdir(passport_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(passport_dir, fname)
        with open(path) as f:
            v1 = json.load(f)
        v2 = convert_v1_to_v2(v1)
        results.append(v2)
    return results

"""Generate passport candidates from family definitions."""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from bot.research.types import PassportCandidate
from bot.research.families import SCORING_FAMILIES, get_param_grid


_id_counter = 0


def generate_passport_id() -> str:
    """Generate a unique passport ID."""
    global _id_counter
    _id_counter += 1
    raw = f"{time.time_ns()}_{_id_counter}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"psp_{h}"


def _make_slug(family_name: str, overrides: dict) -> str:
    """Create human-readable slug from family + key params."""
    parts = [family_name]
    for key in sorted(overrides.keys()):
        if key in ("INDICATOR_WEIGHTS", "USE_ATR_EXITS", "USE_TRAILING_STOP",
                    "MAX_OPEN_POSITIONS_PER_PASSPORT", "MAX_OPEN_POSITIONS_PER_SYMBOL"):
            continue
        val = overrides[key]
        short_key = key.lower().replace("_threshold", "").replace("_spike", "")
        parts.append(f"{short_key}_{val}")
    return "-".join(parts)


def _make_param_summary(overrides: dict) -> str:
    """Create human-readable parameter summary."""
    skip = {"INDICATOR_WEIGHTS", "USE_ATR_EXITS", "USE_TRAILING_STOP",
            "MAX_OPEN_POSITIONS_PER_PASSPORT", "MAX_OPEN_POSITIONS_PER_SYMBOL"}
    parts = []
    for k, v in sorted(overrides.items()):
        if k not in skip:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def generate_passports(
    families: Optional[list[str]] = None,
    max_per_family: Optional[int] = None,
) -> list[PassportCandidate]:
    """Generate passport candidates from family definitions.

    Args:
        families: List of family names to generate from. None = all families.
        max_per_family: Max passports per family (None = no limit).

    Returns:
        List of PassportCandidate instances ready for evaluation.
    """
    if families is None:
        families = list(SCORING_FAMILIES.keys())

    passports = []
    for family_name in families:
        grid = get_param_grid(family_name)
        if not grid:
            continue

        if max_per_family is not None:
            grid = grid[:max_per_family]

        family_def = SCORING_FAMILIES[family_name]
        for overrides in grid:
            slug = _make_slug(family_name, overrides)
            passports.append(PassportCandidate(
                passport_id=generate_passport_id(),
                slug=slug,
                family=family_name,
                config_overrides=overrides,
                description=family_def["description"],
                param_summary=_make_param_summary(overrides),
            ))

    return passports

# Phase 2: Per-Regime Parameter Tuning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `regime_params` in all 26 passport JSONs with thesis-driven per-regime parameter values.

**Architecture:** Python script reads each passport, applies category-based regime_params per the design spec, validates, and writes back. No changes to bot code — only JSON data and docs. Existing integration tests validate the schema automatically.

**Tech Stack:** Python (script), JSON (passport configs), pytest (validation)

**Spec:** `docs/superpowers/specs/2026-04-13-regime-params-tuning-design.md`

---

## Context for Implementers

### Config Resolution Order (3 layers)
1. `bot/config.py` globals (baseline)
2. `passport.config_overrides` (passport-level)
3. `passport.regime_params[current_regime]` (regime-specific — THIS IS WHAT WE'RE POPULATING)

### Key Rules
- `regime_params` only contains values that DIFFER from config_overrides baseline
- CONFIDENCE_THRESHOLD adjustments: `baseline + 4` (where baseline = config_overrides value or global 54)
- MAX_OPEN_POSITIONS_PER_PASSPORT: `min(baseline, cap)` — never increase positions
- DIRECTION_BIAS: only for directional strategies (trend-followers + momentum hybrids)
- Only set params for regimes the passport IS ACTIVE in
- Valid regime_params keys: `CONFIDENCE_THRESHOLD`, `MAX_OPEN_POSITIONS_PER_PASSPORT`, `RISK_PER_TRADE_PCT`, `DIRECTION_BIAS`, `USE_TRAILING_STOP`, `ATR_TRAIL_MULTIPLIER`

### Passport Categories

**Category A — Trend-Following (11):** DualMA Crossover, MinimalEdge, OBV Trend, PureTrend, TrendConfirm, TrendMomentum, Pumpradar Dynamic, Pumpradar HiddenGem, Pumpradar Momentum, Pumpradar Sniper, Pumpradar VolumeKing

**Category B — Mean-Reversion (4):** BBMeanRev, RSIContrarian, Pumpradar ReversalV2, Pumpradar Reversal

**Category C — Breakout (5):** BollingerBreakout, BollingerBreakoutV2, BollingerBreakoutV3, BreakoutVol, Donchian Breakout

**Category D — Hybrid (6):** BalancedSelective, MACDDivergence, PressureReader, RSIMomentumV2, Pumpradar OG Seasonal, Pumpradar OG

---

### Task 1: Create update script and populate all passport regime_params

**Files:**
- Create: `scripts/update_regime_params.py` (temporary, deleted after use)
- Modify: All 26 passport JSONs in `passports/pumpradar/` and `passports/cryptopass-research/`

- [ ] **Step 1: Write the update script**

Create `scripts/update_regime_params.py`:

```python
#!/usr/bin/env python3
"""Populate regime_params for all passports based on Phase 2 design spec.

Design rules:
- TREND_DOWN / HIGH_VOL_CHOP = dangerous regimes → tighten params
- TREND_UP / LOW_VOL_COMPRESSION = home turf → minimal changes
- DIRECTION_BIAS enforced for trend-followers + momentum hybrids only
- CONFIDENCE_THRESHOLD: baseline + 4 in dangerous regimes
- RISK_PER_TRADE_PCT: 0.3 in dangerous regimes
- MAX_OPEN_POSITIONS_PER_PASSPORT: min(baseline, cap) — never increase
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PASSPORT_DIRS = [
    PROJECT_ROOT / "passports" / "pumpradar",
    PROJECT_ROOT / "passports" / "cryptopass-research",
]

GLOBAL_DEFAULTS = {
    "CONFIDENCE_THRESHOLD": 54,
    "MAX_OPEN_POSITIONS_PER_PASSPORT": 50,
    "RISK_PER_TRADE_PCT": 0.5,
}

TREND_FOLLOWING = {
    "DualMA Crossover", "MinimalEdge", "OBV Trend", "PureTrend",
    "TrendConfirm", "TrendMomentum", "Pumpradar Dynamic",
    "Pumpradar HiddenGem", "Pumpradar Momentum", "Pumpradar Sniper",
    "Pumpradar VolumeKing",
}

MEAN_REVERSION = {
    "BBMeanRev", "RSIContrarian", "Pumpradar ReversalV2", "Pumpradar Reversal",
}

BREAKOUT = {
    "BollingerBreakout", "BollingerBreakoutV2", "BollingerBreakoutV3",
    "BreakoutVol", "Donchian Breakout",
}

# Hybrids with DIRECTION_BIAS enforcement (momentum-based)
DIRECTIONAL_HYBRIDS = {
    "BalancedSelective", "PressureReader", "RSIMomentumV2",
    "Pumpradar OG Seasonal", "Pumpradar OG",
}

# Hybrids WITHOUT DIRECTION_BIAS (divergence/regime-neutral)
NON_DIRECTIONAL_HYBRIDS = {
    "MACDDivergence",
}

ALL_CATEGORIES = TREND_FOLLOWING | MEAN_REVERSION | BREAKOUT | DIRECTIONAL_HYBRIDS | NON_DIRECTIONAL_HYBRIDS
VALID_REGIMES = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}


def get_baseline(passport, key):
    """Get effective baseline: config_overrides value or global default."""
    return passport.get("config_overrides", {}).get(key, GLOBAL_DEFAULTS[key])


def compute_regime_params(passport):
    """Compute regime_params based on passport category and active_regimes."""
    name = passport["name"]
    active = set(passport.get("active_regimes") or [])
    if not active:
        return {}

    conf_base = get_baseline(passport, "CONFIDENCE_THRESHOLD")
    max_pos_base = get_baseline(passport, "MAX_OPEN_POSITIONS_PER_PASSPORT")
    params = {}

    if name in TREND_FOLLOWING:
        if "TREND_UP" in active:
            params["TREND_UP"] = {"DIRECTION_BIAS": "LONG_ONLY"}
        if "TREND_DOWN" in active:
            params["TREND_DOWN"] = {
                "DIRECTION_BIAS": "SHORT_ONLY",
                "CONFIDENCE_THRESHOLD": conf_base + 4,
                "RISK_PER_TRADE_PCT": 0.3,
                "MAX_OPEN_POSITIONS_PER_PASSPORT": min(max_pos_base, 15),
            }

    elif name in MEAN_REVERSION:
        if "HIGH_VOL_CHOP" in active:
            chop_params = {"RISK_PER_TRADE_PCT": 0.3}
            # Only set CONFIDENCE_THRESHOLD and MAX_POS if guardrails won't override
            # ReversalV2 (conf=70) and Reversal (conf=85) have guardrails: conf≥80, max_pos≤5
            if name not in ("Pumpradar ReversalV2", "Pumpradar Reversal"):
                chop_params["CONFIDENCE_THRESHOLD"] = conf_base + 4
                chop_params["MAX_OPEN_POSITIONS_PER_PASSPORT"] = min(max_pos_base, 10)
            params["HIGH_VOL_CHOP"] = chop_params
        # LOW_VOL_COMPRESSION: baseline works fine, no changes
        # But we still add an empty entry for documentation purposes? No — spec says only set deltas.

    elif name in BREAKOUT:
        # LOW_VOL_COMPRESSION and TREND_UP: baseline works (home turf)
        if "TREND_DOWN" in active:
            params["TREND_DOWN"] = {
                "CONFIDENCE_THRESHOLD": conf_base + 4,
                "RISK_PER_TRADE_PCT": 0.3,
                "MAX_OPEN_POSITIONS_PER_PASSPORT": min(max_pos_base, 15),
            }

    elif name in DIRECTIONAL_HYBRIDS:
        if "TREND_UP" in active:
            params["TREND_UP"] = {"DIRECTION_BIAS": "LONG_ONLY"}
        if "TREND_DOWN" in active:
            params["TREND_DOWN"] = {
                "DIRECTION_BIAS": "SHORT_ONLY",
                "CONFIDENCE_THRESHOLD": conf_base + 4,
                "RISK_PER_TRADE_PCT": 0.3,
                "MAX_OPEN_POSITIONS_PER_PASSPORT": min(max_pos_base, 15),
            }
        if "HIGH_VOL_CHOP" in active:
            params["HIGH_VOL_CHOP"] = {
                "CONFIDENCE_THRESHOLD": conf_base + 4,
                "RISK_PER_TRADE_PCT": 0.3,
                "MAX_OPEN_POSITIONS_PER_PASSPORT": min(max_pos_base, 10),
            }

    elif name in NON_DIRECTIONAL_HYBRIDS:
        # No DIRECTION_BIAS — divergences are inherently counter-trend
        if "TREND_DOWN" in active:
            params["TREND_DOWN"] = {
                "CONFIDENCE_THRESHOLD": conf_base + 4,
                "RISK_PER_TRADE_PCT": 0.3,
                "MAX_OPEN_POSITIONS_PER_PASSPORT": min(max_pos_base, 15),
            }
        if "HIGH_VOL_CHOP" in active:
            params["HIGH_VOL_CHOP"] = {
                "CONFIDENCE_THRESHOLD": conf_base + 4,
                "RISK_PER_TRADE_PCT": 0.3,
                "MAX_OPEN_POSITIONS_PER_PASSPORT": min(max_pos_base, 10),
            }

    else:
        print(f"  WARNING: {name} not in any category — skipping regime_params")
        return {}

    return params


def validate_params(name, params, active_regimes):
    """Validate computed regime_params against rules."""
    active = set(active_regimes or [])
    for regime, rp in params.items():
        assert regime in VALID_REGIMES, f"{name}: invalid regime '{regime}'"
        assert regime in active, f"{name}: regime '{regime}' not in active_regimes {active}"
        for key in rp:
            assert key in {
                "CONFIDENCE_THRESHOLD", "MAX_OPEN_POSITIONS_PER_PASSPORT",
                "RISK_PER_TRADE_PCT", "DIRECTION_BIAS",
                "USE_TRAILING_STOP", "ATR_TRAIL_MULTIPLIER",
            }, f"{name}: invalid key '{key}'"
        if "CONFIDENCE_THRESHOLD" in rp:
            assert 50 <= rp["CONFIDENCE_THRESHOLD"] <= 95, f"{name}: CONFIDENCE_THRESHOLD {rp['CONFIDENCE_THRESHOLD']} out of range"
        if "RISK_PER_TRADE_PCT" in rp:
            assert 0.1 <= rp["RISK_PER_TRADE_PCT"] <= 1.0, f"{name}: RISK_PER_TRADE_PCT {rp['RISK_PER_TRADE_PCT']} out of range"
        if "DIRECTION_BIAS" in rp:
            assert rp["DIRECTION_BIAS"] in ("LONG_ONLY", "SHORT_ONLY"), f"{name}: invalid DIRECTION_BIAS '{rp['DIRECTION_BIAS']}'"


def main():
    dry_run = "--dry-run" in sys.argv
    updated = 0
    skipped = 0
    errors = []

    for pdir in PASSPORT_DIRS:
        if not pdir.is_dir():
            continue
        for fname in sorted(os.listdir(pdir)):
            if not fname.endswith(".json"):
                continue
            fpath = pdir / fname
            with open(fpath) as f:
                passport = json.load(f)

            name = passport["name"]
            if name not in ALL_CATEGORIES:
                print(f"  SKIP: {name} — not in any category")
                skipped += 1
                continue

            params = compute_regime_params(passport)
            try:
                validate_params(name, params, passport.get("active_regimes"))
            except AssertionError as e:
                errors.append(str(e))
                print(f"  ERROR: {e}")
                continue

            passport["regime_params"] = params
            if dry_run:
                print(f"  DRY-RUN: {name:30s} → {json.dumps(params, separators=(',', ':'))}")
            else:
                with open(fpath, "w") as f:
                    json.dump(passport, f, indent=2)
                    f.write("\n")
                print(f"  UPDATED: {name:30s} → {len(params)} regime(s) tuned")
            updated += 1

    print(f"\n{'DRY-RUN ' if dry_run else ''}Summary: {updated} updated, {skipped} skipped, {len(errors)} errors")
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run to verify computed values**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && uv run python scripts/update_regime_params.py --dry-run`

Expected: All 26 passports listed with computed regime_params, 0 errors. Verify a few manually:
- `DualMA Crossover` → TREND_UP: `{DIRECTION_BIAS: LONG_ONLY}`, TREND_DOWN: `{DIRECTION_BIAS: SHORT_ONLY, CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}`
- `BBMeanRev` → HIGH_VOL_CHOP: `{CONFIDENCE_THRESHOLD: 64, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}`
- `Pumpradar ReversalV2` → HIGH_VOL_CHOP: `{RISK_PER_TRADE_PCT: 0.3}` (no conf/max_pos — guardrails handle those)
- `BollingerBreakout` → TREND_DOWN: `{CONFIDENCE_THRESHOLD: 59, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}`

- [ ] **Step 3: Run for real to update all passport JSONs**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && uv run python scripts/update_regime_params.py`

Expected: "Summary: 26 updated, 0 skipped, 0 errors"

- [ ] **Step 4: Run integration tests to validate schema**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && uv run pytest tests/test_regime_gating_integration.py -v --tb=short`

Expected: All 104 tests pass (26 passports × 4 validations). Key: `test_passport_regime_params_only_for_active_regimes` must pass (regime_params keys ⊂ active_regimes).

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && uv run pytest tests/ -v --tb=short 2>&1 | tail -20`

Expected: 505+ tests pass, 0 failures.

- [ ] **Step 6: Commit passport updates**

```bash
cd /Users/faiqnau/fight/trading/crypto-signal
git add passports/pumpradar/*.json passports/cryptopass-research/*.json
git commit -m "feat: populate regime_params for all 26 passports (Phase 2)

Thesis-driven per-regime parameter tuning:
- Trend-followers: LONG_ONLY in TREND_UP, SHORT_ONLY + tightened params in TREND_DOWN
- Mean-reversion: higher confidence + lower risk in HIGH_VOL_CHOP
- Breakout: tightened params in TREND_DOWN only
- Hybrids: individual treatment based on strategy thesis

Parameters adjusted per dangerous regime:
- CONFIDENCE_THRESHOLD: baseline + 4
- RISK_PER_TRADE_PCT: 0.5 -> 0.3
- MAX_OPEN_POSITIONS_PER_PASSPORT: capped at 15 (TREND_DOWN) or 10 (HIGH_VOL_CHOP)
- DIRECTION_BIAS: LONG_ONLY/SHORT_ONLY for directional strategies

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

- [ ] **Step 7: Delete temporary script**

```bash
rm scripts/update_regime_params.py
```

---

### Task 2: Add regime_params value validation tests

**Files:**
- Create: `tests/test_regime_params_values.py`

These tests validate the COMPUTED VALUES (not just schema) — ensuring the thesis is correctly applied.

- [ ] **Step 1: Write value validation tests**

Create `tests/test_regime_params_values.py`:

```python
"""Validate Phase 2 regime_params values match thesis-driven design rules.

Rules:
1. Trend-followers get DIRECTION_BIAS in trending regimes
2. CONFIDENCE_THRESHOLD in dangerous regimes = baseline + 4
3. RISK_PER_TRADE_PCT = 0.3 in dangerous regimes
4. MAX_OPEN_POSITIONS_PER_PASSPORT <= baseline (never increases)
5. Mean-reversion passports have no DIRECTION_BIAS
6. Breakout passports have no DIRECTION_BIAS
"""
import json
import os
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PASSPORT_DIRS = [
    PROJECT_ROOT / "passports" / "pumpradar",
    PROJECT_ROOT / "passports" / "cryptopass-research",
]

GLOBAL_CONF_THRESHOLD = 54
GLOBAL_MAX_POS = 50

TREND_FOLLOWING = {
    "DualMA Crossover", "MinimalEdge", "OBV Trend", "PureTrend",
    "TrendConfirm", "TrendMomentum", "Pumpradar Dynamic",
    "Pumpradar HiddenGem", "Pumpradar Momentum", "Pumpradar Sniper",
    "Pumpradar VolumeKing",
}

MEAN_REVERSION = {
    "BBMeanRev", "RSIContrarian", "Pumpradar ReversalV2", "Pumpradar Reversal",
}

BREAKOUT = {
    "BollingerBreakout", "BollingerBreakoutV2", "BollingerBreakoutV3",
    "BreakoutVol", "Donchian Breakout",
}

DIRECTIONAL_HYBRIDS = {
    "BalancedSelective", "PressureReader", "RSIMomentumV2",
    "Pumpradar OG Seasonal", "Pumpradar OG",
}


def _load_all_passports():
    passports = []
    for d in PASSPORT_DIRS:
        if not d.is_dir():
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                with open(d / fname) as f:
                    passports.append(json.load(f))
    assert passports, "No passport JSON files found"
    return passports


ALL_PASSPORTS = _load_all_passports()


def _get_baseline(passport, key, default):
    return passport.get("config_overrides", {}).get(key, default)


@pytest.fixture(params=ALL_PASSPORTS, ids=lambda p: p["name"])
def passport(request):
    return request.param


class TestTrendFollowerDirectionBias:
    """Trend-followers must have DIRECTION_BIAS in trending regimes."""

    @pytest.fixture(params=[p for p in ALL_PASSPORTS if p["name"] in TREND_FOLLOWING],
                    ids=lambda p: p["name"])
    def tf_passport(self, request):
        return request.param

    def test_long_only_in_trend_up(self, tf_passport):
        rp = tf_passport.get("regime_params", {})
        if "TREND_UP" in (tf_passport.get("active_regimes") or []):
            assert "TREND_UP" in rp, f"{tf_passport['name']}: missing TREND_UP regime_params"
            assert rp["TREND_UP"].get("DIRECTION_BIAS") == "LONG_ONLY", (
                f"{tf_passport['name']}: expected LONG_ONLY in TREND_UP"
            )

    def test_short_only_in_trend_down(self, tf_passport):
        rp = tf_passport.get("regime_params", {})
        if "TREND_DOWN" in (tf_passport.get("active_regimes") or []):
            assert "TREND_DOWN" in rp, f"{tf_passport['name']}: missing TREND_DOWN regime_params"
            assert rp["TREND_DOWN"].get("DIRECTION_BIAS") == "SHORT_ONLY", (
                f"{tf_passport['name']}: expected SHORT_ONLY in TREND_DOWN"
            )


class TestDangerousRegimeTightening:
    """TREND_DOWN and HIGH_VOL_CHOP should have tightened parameters."""

    def test_trend_down_risk_reduction(self, passport):
        rp = passport.get("regime_params", {})
        td = rp.get("TREND_DOWN", {})
        if td and "RISK_PER_TRADE_PCT" in td:
            assert td["RISK_PER_TRADE_PCT"] == 0.3, (
                f"{passport['name']}: TREND_DOWN risk should be 0.3"
            )

    def test_high_vol_chop_risk_reduction(self, passport):
        rp = passport.get("regime_params", {})
        hvc = rp.get("HIGH_VOL_CHOP", {})
        if hvc and "RISK_PER_TRADE_PCT" in hvc:
            assert hvc["RISK_PER_TRADE_PCT"] == 0.3, (
                f"{passport['name']}: HIGH_VOL_CHOP risk should be 0.3"
            )

    def test_confidence_threshold_is_baseline_plus_4(self, passport):
        rp = passport.get("regime_params", {})
        conf_base = _get_baseline(passport, "CONFIDENCE_THRESHOLD", GLOBAL_CONF_THRESHOLD)
        for regime in ("TREND_DOWN", "HIGH_VOL_CHOP"):
            regime_rp = rp.get(regime, {})
            if "CONFIDENCE_THRESHOLD" in regime_rp:
                assert regime_rp["CONFIDENCE_THRESHOLD"] == conf_base + 4, (
                    f"{passport['name']}: {regime} CONFIDENCE_THRESHOLD should be "
                    f"{conf_base} + 4 = {conf_base + 4}, got {regime_rp['CONFIDENCE_THRESHOLD']}"
                )


class TestMaxPositionsNeverIncrease:
    """MAX_OPEN_POSITIONS_PER_PASSPORT in regime_params must not exceed baseline."""

    def test_max_pos_capped(self, passport):
        rp = passport.get("regime_params", {})
        max_pos_base = _get_baseline(passport, "MAX_OPEN_POSITIONS_PER_PASSPORT", GLOBAL_MAX_POS)
        for regime, params in rp.items():
            if "MAX_OPEN_POSITIONS_PER_PASSPORT" in params:
                assert params["MAX_OPEN_POSITIONS_PER_PASSPORT"] <= max_pos_base, (
                    f"{passport['name']}: {regime} MAX_POS {params['MAX_OPEN_POSITIONS_PER_PASSPORT']} "
                    f"> baseline {max_pos_base}"
                )


class TestMeanReversionNoDirectionBias:
    """Mean-reversion passports should NOT have DIRECTION_BIAS."""

    @pytest.fixture(params=[p for p in ALL_PASSPORTS if p["name"] in MEAN_REVERSION],
                    ids=lambda p: p["name"])
    def mr_passport(self, request):
        return request.param

    def test_no_direction_bias(self, mr_passport):
        rp = mr_passport.get("regime_params", {})
        for regime, params in rp.items():
            assert "DIRECTION_BIAS" not in params, (
                f"{mr_passport['name']}: mean-reversion should not have DIRECTION_BIAS in {regime}"
            )


class TestBreakoutNoDirectionBias:
    """Breakout passports should NOT have DIRECTION_BIAS."""

    @pytest.fixture(params=[p for p in ALL_PASSPORTS if p["name"] in BREAKOUT],
                    ids=lambda p: p["name"])
    def bo_passport(self, request):
        return request.param

    def test_no_direction_bias(self, bo_passport):
        rp = bo_passport.get("regime_params", {})
        for regime, params in rp.items():
            assert "DIRECTION_BIAS" not in params, (
                f"{bo_passport['name']}: breakout should not have DIRECTION_BIAS in {regime}"
            )
```

- [ ] **Step 2: Run the new value validation tests**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && uv run pytest tests/test_regime_params_values.py -v --tb=short 2>&1 | tail -40`

Expected: All tests pass. The exact count depends on parametrization (26 passports × multiple test classes).

- [ ] **Step 3: Commit test file**

```bash
cd /Users/faiqnau/fight/trading/crypto-signal
git add tests/test_regime_params_values.py
git commit -m "test: add Phase 2 regime_params value validation tests

Validates thesis-driven design rules:
- Trend-followers have DIRECTION_BIAS in trending regimes
- Dangerous regimes (TREND_DOWN, HIGH_VOL_CHOP) have tightened params
- CONFIDENCE_THRESHOLD = baseline + 4 in dangerous regimes
- MAX_OPEN_POSITIONS_PER_PASSPORT never exceeds passport baseline
- Mean-reversion and breakout have no DIRECTION_BIAS

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Update documentation and deploy

**Files:**
- Modify: `passports/VERSIONS.md`
- Modify: `docs/FINDINGS.md`

- [ ] **Step 1: Update VERSIONS.md**

Add a new section to `passports/VERSIONS.md` documenting the Phase 2 changes. Include:

```markdown
## Session 11f — Phase 2: Per-Regime Parameter Tuning (2026-04-13)

All 26 passports now have thesis-driven `regime_params` for per-regime behavior tuning.

### Design Rules Applied
- **TREND_DOWN:** +4 confidence, 0.3% risk, max 15 positions, SHORT_ONLY for directional strategies
- **HIGH_VOL_CHOP:** +4 confidence, 0.3% risk, max 10 positions
- **TREND_UP:** LONG_ONLY for directional strategies, standard params otherwise
- **LOW_VOL_COMPRESSION:** Standard params (clean signals, no adjustment needed)

### Category Assignments
| Category | Passports | DIRECTION_BIAS? |
|----------|-----------|-----------------|
| Trend-Following (11) | DualMA, MinimalEdge, OBV Trend, PureTrend, TrendConfirm, TrendMomentum, Dynamic, HiddenGem, Momentum, Sniper, VolumeKing | ✅ LONG_ONLY / SHORT_ONLY |
| Mean-Reversion (4) | BBMeanRev, RSIContrarian, ReversalV2, Reversal | ❌ Always BOTH |
| Breakout (5) | BollingerBreakout (v1/v2/v3), BreakoutVol, Donchian | ❌ Always BOTH |
| Hybrid-Directional (5) | BalancedSelective, PressureReader, RSIMomentumV2, OG Seasonal, OG | ✅ LONG_ONLY / SHORT_ONLY |
| Hybrid-Neutral (1) | MACDDivergence | ❌ Always BOTH |
```

- [ ] **Step 2: Update FINDINGS.md**

Add a new subsection under the existing §21 (or create §22) in `docs/FINDINGS.md`:

```markdown
### §22 Phase 2: Per-Regime Parameter Tuning (Session 11f)

**What:** Populated `regime_params` for all 26 passports with thesis-driven values.

**Core thesis:** Dangerous regimes (TREND_DOWN, HIGH_VOL_CHOP) get tightened parameters. Home regimes get minimal changes. Direction-following strategies enforce DIRECTION_BIAS.

**Key parameters per dangerous regime:**
- CONFIDENCE_THRESHOLD: baseline + 4 (higher conviction required)
- RISK_PER_TRADE_PCT: 0.3% (down from 0.5%, 40% risk reduction)
- MAX_OPEN_POSITIONS_PER_PASSPORT: capped at 15 (TREND_DOWN) or 10 (HIGH_VOL_CHOP)
- DIRECTION_BIAS: LONG_ONLY in TREND_UP, SHORT_ONLY in TREND_DOWN (directional strategies only)

**What this means for live trading:**
1. In bull markets: trend-followers only go LONG (no counter-trend shorts)
2. In bear markets: 40% less risk per trade, fewer positions, higher confidence bar
3. In choppy markets: mean-reversion fires only on high-conviction setups
4. In compression: standard behavior (signals are clean)

**Expected impact:** Fewer losing trades in adverse regimes, same profitable trades in favorable regimes. Net positive Sharpe ratio improvement.
```

- [ ] **Step 3: Commit documentation updates**

```bash
cd /Users/faiqnau/fight/trading/crypto-signal
git add passports/VERSIONS.md docs/FINDINGS.md
git commit -m "docs: Phase 2 regime_params tuning documentation

Updated VERSIONS.md with category assignments and design rules.
Added FINDINGS.md §22 documenting thesis, parameters, and expected impact.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

- [ ] **Step 4: Run final full test suite**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && uv run pytest tests/ -v --tb=short 2>&1 | tail -20`

Expected: All tests pass (505 existing + new value validation tests).

- [ ] **Step 5: Push and deploy to VPS**

```bash
cd /Users/faiqnau/fight/trading/crypto-signal
git push origin master
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && sudo systemctl restart cryptopass.service"
ssh fight-tres "sleep 3 && sudo systemctl status cryptopass.service --no-pager"
ssh fight-tres "sleep 10 && sudo journalctl -u cryptopass.service -n 30 --no-pager -o short-iso"
```

Expected:
- Service active (running)
- Logs show passports loading with regime_params
- First scan shows "applying regime_params for [REGIME]" log lines
- DIRECTION_BIAS passports respect LONG_ONLY/SHORT_ONLY in scan signals

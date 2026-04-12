"""Validate Phase 2 regime_params values match thesis-driven design rules.

Rules:
1. Trend-followers get DIRECTION_BIAS in trending regimes (TREND_UP→LONG_ONLY, TREND_DOWN→SHORT_ONLY)
2. Directional hybrids get DIRECTION_BIAS in trending regimes they're active in
3. CONFIDENCE_THRESHOLD in dangerous regimes = baseline + 4
4. RISK_PER_TRADE_PCT = 0.3 in dangerous regimes (when set)
5. MAX_OPEN_POSITIONS_PER_PASSPORT never exceeds baseline
6. Mean-reversion passports have NO DIRECTION_BIAS in any regime
7. Breakout passports have NO DIRECTION_BIAS in any regime
8. MACDDivergence (non-directional hybrid) has NO DIRECTION_BIAS
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

NON_DIRECTIONAL_HYBRIDS = {"MACDDivergence"}

NO_DIRECTION_BIAS = MEAN_REVERSION | BREAKOUT | NON_DIRECTIONAL_HYBRIDS
DIRECTIONAL = TREND_FOLLOWING | DIRECTIONAL_HYBRIDS

DANGEROUS_REGIMES = {"TREND_DOWN", "HIGH_VOL_CHOP"}

# Passports exempt from dangerous-regime RISK enforcement because their baselines
# are already tighter than the caps (guardrails handle CONF/MAX_POS for these).
# ReversalV2: conf=70 → guardrail bumps to 80, max_pos=3 (already ≤5)
# Reversal: conf=85 (above 80 floor), max_pos=5 (at guardrail cap)
# Both still get RISK_PER_TRADE_PCT=0.3 — only CONF/MAX_POS are exempt.
CONF_MAXPOS_EXEMPT = {"Pumpradar ReversalV2", "Pumpradar Reversal"}


def _load_all_passports():
    passports = []
    for d in PASSPORT_DIRS:
        if not d.is_dir():
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                with open(d / fname) as f:
                    passports.append(json.load(f))
    assert passports, "No passport JSON files found — check PASSPORT_DIRS"
    return passports


ALL_PASSPORTS = _load_all_passports()


def _get_baseline(passport, key, default):
    return passport.get("config_overrides", {}).get(key, default)


def _active_regimes(passport):
    return set(passport.get("active_regimes") or [])


def _regime_params(passport):
    return passport.get("regime_params", {})


# --- Fixtures ---

@pytest.fixture(params=ALL_PASSPORTS, ids=lambda p: p["name"])
def passport(request):
    return request.param


@pytest.fixture(
    params=[p for p in ALL_PASSPORTS if p["name"] in TREND_FOLLOWING],
    ids=lambda p: p["name"],
)
def tf_passport(request):
    return request.param


@pytest.fixture(
    params=[p for p in ALL_PASSPORTS if p["name"] in DIRECTIONAL_HYBRIDS],
    ids=lambda p: p["name"],
)
def dh_passport(request):
    return request.param


@pytest.fixture(
    params=[p for p in ALL_PASSPORTS if p["name"] in MEAN_REVERSION],
    ids=lambda p: p["name"],
)
def mr_passport(request):
    return request.param


@pytest.fixture(
    params=[p for p in ALL_PASSPORTS if p["name"] in BREAKOUT],
    ids=lambda p: p["name"],
)
def bo_passport(request):
    return request.param


# --- Rule 1: Trend-followers get DIRECTION_BIAS in trending regimes ---

class TestTrendFollowerDirectionBias:
    """Trend-following passports must enforce DIRECTION_BIAS in trending regimes."""

    def test_long_only_in_trend_up(self, tf_passport):
        active = _active_regimes(tf_passport)
        if "TREND_UP" not in active:
            pytest.skip(f"{tf_passport['name']} not active in TREND_UP")
        rp = _regime_params(tf_passport)
        assert "TREND_UP" in rp, (
            f"{tf_passport['name']}: missing TREND_UP in regime_params "
            f"(active_regimes={active})"
        )
        assert rp["TREND_UP"].get("DIRECTION_BIAS") == "LONG_ONLY", (
            f"{tf_passport['name']}: expected DIRECTION_BIAS=LONG_ONLY in TREND_UP, "
            f"got {rp['TREND_UP'].get('DIRECTION_BIAS')!r}"
        )

    def test_short_only_in_trend_down(self, tf_passport):
        active = _active_regimes(tf_passport)
        if "TREND_DOWN" not in active:
            pytest.skip(f"{tf_passport['name']} not active in TREND_DOWN")
        rp = _regime_params(tf_passport)
        assert "TREND_DOWN" in rp, (
            f"{tf_passport['name']}: missing TREND_DOWN in regime_params "
            f"(active_regimes={active})"
        )
        assert rp["TREND_DOWN"].get("DIRECTION_BIAS") == "SHORT_ONLY", (
            f"{tf_passport['name']}: expected DIRECTION_BIAS=SHORT_ONLY in TREND_DOWN, "
            f"got {rp['TREND_DOWN'].get('DIRECTION_BIAS')!r}"
        )


# --- Rule 2: Directional hybrids get DIRECTION_BIAS in trending regimes ---

class TestDirectionalHybridDirectionBias:
    """Directional-hybrid passports must enforce DIRECTION_BIAS in trending regimes they're active in."""

    def test_long_only_in_trend_up(self, dh_passport):
        active = _active_regimes(dh_passport)
        if "TREND_UP" not in active:
            pytest.skip(f"{dh_passport['name']} not active in TREND_UP")
        rp = _regime_params(dh_passport)
        assert "TREND_UP" in rp, (
            f"{dh_passport['name']}: missing TREND_UP in regime_params "
            f"(active_regimes={active})"
        )
        assert rp["TREND_UP"].get("DIRECTION_BIAS") == "LONG_ONLY", (
            f"{dh_passport['name']}: expected DIRECTION_BIAS=LONG_ONLY in TREND_UP, "
            f"got {rp['TREND_UP'].get('DIRECTION_BIAS')!r}"
        )

    def test_short_only_in_trend_down(self, dh_passport):
        active = _active_regimes(dh_passport)
        if "TREND_DOWN" not in active:
            pytest.skip(f"{dh_passport['name']} not active in TREND_DOWN")
        rp = _regime_params(dh_passport)
        assert "TREND_DOWN" in rp, (
            f"{dh_passport['name']}: missing TREND_DOWN in regime_params "
            f"(active_regimes={active})"
        )
        assert rp["TREND_DOWN"].get("DIRECTION_BIAS") == "SHORT_ONLY", (
            f"{dh_passport['name']}: expected DIRECTION_BIAS=SHORT_ONLY in TREND_DOWN, "
            f"got {rp['TREND_DOWN'].get('DIRECTION_BIAS')!r}"
        )


# --- Rule 3 & 4: Dangerous regimes are tightened ---

class TestDangerousRegimeTightening:
    """TREND_DOWN and HIGH_VOL_CHOP entries must have tightened params when present."""

    def test_trend_down_risk_reduction(self, passport):
        td = _regime_params(passport).get("TREND_DOWN", {})
        if "RISK_PER_TRADE_PCT" not in td:
            pytest.skip(f"{passport['name']} TREND_DOWN has no RISK_PER_TRADE_PCT")
        assert td["RISK_PER_TRADE_PCT"] == 0.3, (
            f"{passport['name']}: TREND_DOWN RISK_PER_TRADE_PCT should be 0.3, "
            f"got {td['RISK_PER_TRADE_PCT']}"
        )

    def test_high_vol_chop_risk_reduction(self, passport):
        hvc = _regime_params(passport).get("HIGH_VOL_CHOP", {})
        if "RISK_PER_TRADE_PCT" not in hvc:
            pytest.skip(f"{passport['name']} HIGH_VOL_CHOP has no RISK_PER_TRADE_PCT")
        assert hvc["RISK_PER_TRADE_PCT"] == 0.3, (
            f"{passport['name']}: HIGH_VOL_CHOP RISK_PER_TRADE_PCT should be 0.3, "
            f"got {hvc['RISK_PER_TRADE_PCT']}"
        )

    def test_confidence_threshold_is_baseline_plus_4(self, passport):
        rp = _regime_params(passport)
        conf_base = _get_baseline(passport, "CONFIDENCE_THRESHOLD", GLOBAL_CONF_THRESHOLD)
        for regime in ("TREND_DOWN", "HIGH_VOL_CHOP"):
            regime_rp = rp.get(regime, {})
            if "CONFIDENCE_THRESHOLD" not in regime_rp:
                continue
            expected = conf_base + 4
            actual = regime_rp["CONFIDENCE_THRESHOLD"]
            assert actual == expected, (
                f"{passport['name']}: {regime} CONFIDENCE_THRESHOLD should be "
                f"baseline({conf_base}) + 4 = {expected}, got {actual}"
            )


# --- Rule 5: MAX_OPEN_POSITIONS_PER_PASSPORT never exceeds baseline ---

class TestMaxPositionsNeverIncrease:
    """MAX_OPEN_POSITIONS_PER_PASSPORT in any regime must not exceed the passport baseline."""

    def test_max_pos_capped_at_baseline(self, passport):
        rp = _regime_params(passport)
        max_pos_base = _get_baseline(passport, "MAX_OPEN_POSITIONS_PER_PASSPORT", GLOBAL_MAX_POS)
        for regime, params in rp.items():
            if "MAX_OPEN_POSITIONS_PER_PASSPORT" not in params:
                continue
            regime_cap = params["MAX_OPEN_POSITIONS_PER_PASSPORT"]
            assert regime_cap <= max_pos_base, (
                f"{passport['name']}: {regime} MAX_OPEN_POSITIONS_PER_PASSPORT={regime_cap} "
                f"exceeds passport baseline={max_pos_base}"
            )


# --- Rules 6 & 7: Mean-reversion and breakout have NO DIRECTION_BIAS ---

class TestMeanReversionNoDirectionBias:
    """Mean-reversion passports must NOT have DIRECTION_BIAS in any regime."""

    def test_no_direction_bias(self, mr_passport):
        rp = _regime_params(mr_passport)
        violations = [
            regime for regime, params in rp.items() if "DIRECTION_BIAS" in params
        ]
        assert not violations, (
            f"{mr_passport['name']}: mean-reversion should not have DIRECTION_BIAS, "
            f"but found it in: {violations}"
        )


class TestBreakoutNoDirectionBias:
    """Breakout passports must NOT have DIRECTION_BIAS in any regime."""

    def test_no_direction_bias(self, bo_passport):
        rp = _regime_params(bo_passport)
        violations = [
            regime for regime, params in rp.items() if "DIRECTION_BIAS" in params
        ]
        assert not violations, (
            f"{bo_passport['name']}: breakout should not have DIRECTION_BIAS, "
            f"but found it in: {violations}"
        )


# --- Rule 8: MACDDivergence (non-directional hybrid) has NO DIRECTION_BIAS ---

class TestNonDirectionalHybridNoDirectionBias:
    """MACDDivergence must not receive DIRECTION_BIAS (divergences are regime-neutral)."""

    def test_macd_divergence_no_direction_bias(self):
        macd = next(
            (p for p in ALL_PASSPORTS if p["name"] == "MACDDivergence"), None
        )
        assert macd is not None, "MACDDivergence passport not found"
        rp = _regime_params(macd)
        violations = [
            regime for regime, params in rp.items() if "DIRECTION_BIAS" in params
        ]
        assert not violations, (
            f"MACDDivergence should not have DIRECTION_BIAS, "
            f"but found it in: {violations}"
        )


# --- Rule 9: Dangerous regimes MUST have safety params ---

class TestDangerousRegimeParamsMustExist:
    """Passports active in TREND_DOWN or HIGH_VOL_CHOP must define safety params.

    Every passport active in a dangerous regime must have RISK_PER_TRADE_PCT=0.3
    in its regime_params for that regime. CONFIDENCE_THRESHOLD and MAX_POS are
    also required unless the passport is in CONF_MAXPOS_EXEMPT (reversal passports
    whose baselines already exceed the guardrail floors).

    Note on Sniper (conf=74 in TREND_DOWN): the +4 rule produces a threshold
    below Sniper's min achievable confidence (75%), making it a no-op. This is
    accepted for consistency — the other TREND_DOWN params (SHORT_ONLY, 0.3%
    risk, 15 max_pos) provide the real protection.
    """

    def test_dangerous_regime_has_risk_param(self, passport):
        """All passports active in dangerous regimes must set RISK_PER_TRADE_PCT."""
        active = _active_regimes(passport)
        rp = _regime_params(passport)
        for regime in DANGEROUS_REGIMES & active:
            assert regime in rp, (
                f"{passport['name']}: active in {regime} (dangerous) but "
                f"missing from regime_params entirely"
            )
            assert "RISK_PER_TRADE_PCT" in rp[regime], (
                f"{passport['name']}: active in {regime} (dangerous) but "
                f"missing RISK_PER_TRADE_PCT safety param"
            )

    def test_dangerous_regime_has_confidence_param(self, passport):
        """Non-exempt passports in dangerous regimes must set CONFIDENCE_THRESHOLD."""
        name = passport["name"]
        if name in CONF_MAXPOS_EXEMPT:
            pytest.skip(f"{name} exempt from CONF/MAX_POS enforcement (guardrails handle it)")
        active = _active_regimes(passport)
        rp = _regime_params(passport)
        for regime in DANGEROUS_REGIMES & active:
            assert "CONFIDENCE_THRESHOLD" in rp.get(regime, {}), (
                f"{name}: active in {regime} (dangerous) but "
                f"missing CONFIDENCE_THRESHOLD safety param"
            )

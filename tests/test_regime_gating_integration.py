"""Integration tests: verify all production passport JSONs have valid regime config."""
import json
import os
import pytest

VALID_REGIMES = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
VALID_REGIME_PARAM_KEYS = {
    "CONFIDENCE_THRESHOLD", "MAX_OPEN_POSITIONS_PER_PASSPORT",
    "RISK_PER_TRADE_PCT", "DIRECTION_BIAS",
    "USE_TRAILING_STOP", "ATR_TRAIL_MULTIPLIER",
}
PASSPORT_DIRS = ["passports/pumpradar", "passports/cryptopass-research"]


def _all_passport_paths():
    paths = []
    for d in PASSPORT_DIRS:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                paths.append(os.path.join(d, fname))
    return paths


@pytest.fixture(params=_all_passport_paths(), ids=lambda p: os.path.basename(p))
def passport_data(request):
    with open(request.param) as f:
        return json.load(f)


def test_passport_has_active_regimes(passport_data):
    """Every passport must declare active_regimes (list or null)."""
    ar = passport_data.get("active_regimes")
    assert "active_regimes" in passport_data, f"{passport_data['name']}: missing active_regimes key"
    if ar is not None:
        assert isinstance(ar, list), f"{passport_data['name']}: active_regimes must be list or null"
        for r in ar:
            assert r in VALID_REGIMES, f"{passport_data['name']}: invalid regime '{r}'"


def test_passport_regime_params_schema(passport_data):
    """regime_params must be a dict with valid regime keys and valid param keys."""
    rp = passport_data.get("regime_params", {})
    assert isinstance(rp, dict), f"{passport_data['name']}: regime_params must be dict"

    for regime, params in rp.items():
        assert regime in VALID_REGIMES, f"{passport_data['name']}: invalid regime key '{regime}' in regime_params"
        assert isinstance(params, dict), f"{passport_data['name']}: regime_params[{regime}] must be dict"

        for key in params:
            assert key in VALID_REGIME_PARAM_KEYS, (
                f"{passport_data['name']}: unknown regime_params key '{key}' "
                f"in {regime}. Valid: {VALID_REGIME_PARAM_KEYS}"
            )


def test_passport_regime_params_only_for_active_regimes(passport_data):
    """regime_params keys should only reference regimes in active_regimes."""
    ar = passport_data.get("active_regimes")
    rp = passport_data.get("regime_params", {})

    if ar is None or not rp:
        return

    for regime in rp:
        assert regime in ar, (
            f"{passport_data['name']}: regime_params has key '{regime}' "
            f"but active_regimes is {ar}"
        )


def test_all_8_indicator_weights_present(passport_data):
    """All 8 INDICATOR_WEIGHTS keys must be present (existing invariant)."""
    required_keys = {
        "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
        "bb_position", "volume_spike", "pressure", "candle_direction",
    }
    co = passport_data.get("config_overrides", {})
    iw = co.get("INDICATOR_WEIGHTS", {})

    weight_keys = {k for k in iw if k in required_keys}
    missing = required_keys - weight_keys
    assert not missing, f"{passport_data['name']}: missing INDICATOR_WEIGHTS: {missing}"

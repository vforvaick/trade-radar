from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _simulate_equity(ledger: pd.DataFrame) -> float:
    equity = 1000.0
    resolved = ledger[ledger["status"] != "OPEN"].copy()
    for _, row in resolved.sort_values("date_signal").iterrows():
        risk = equity * 0.03
        if row["status"] == "SL_CLOSED":
            equity -= risk
        elif row["tp1_hit"]:
            entry = row["entry_price"]
            sl = row["sl_target"]
            tp1 = row["tp1_target"]
            if pd.isna(sl) or pd.isna(entry) or pd.isna(tp1):
                continue
            sl_d = abs(sl - entry) / entry
            tp1_d = abs(tp1 - entry) / entry
            gain = risk * (tp1_d / sl_d) * 0.70
            if row["tp2_hit"] and not pd.isna(row["tp2_target"]):
                tp2_d = abs(row["tp2_target"] - entry) / entry
                gain += risk * (tp2_d / sl_d) * 0.20
            if row["tp3_hit"] and not pd.isna(row["tp3_target"]):
                tp3_d = abs(row["tp3_target"] - entry) / entry
                gain += risk * (tp3_d / sl_d) * 0.10
            equity += gain
    return equity


@pytest.fixture
def validated_ledger() -> pd.DataFrame:
    ledger_path = Path(__file__).resolve().parents[1] / "data" / "validated_ledger.csv"
    return pd.read_csv(ledger_path)


def test_validated_ledger_simulation_is_deterministic(validated_ledger):
    resolved = validated_ledger[validated_ledger["status"] != "OPEN"]
    equity = _simulate_equity(validated_ledger)

    assert len(resolved) == 49
    assert equity == pytest.approx(1296.2821160602, rel=0, abs=1e-9)
    assert (equity / 1000.0 - 1.0) * 100 == pytest.approx(29.628211606, rel=0, abs=1e-9)

"""Tests for the PnL engine: leverage multiplier, trading fees, trade log fields, equity snapshots."""
import json
from datetime import datetime

import pytest

from bot import config
from bot.position_manager import Position, PositionManager
from bot.signals import Signal
from bot.state_store import StateStore


def _make_signal(
    direction="LONG",
    entry=1000.0,
    sl=900.0,     # 10% below entry
    tp1=1100.0,   # 10% above entry — same distance as SL
    tp2=1261.0,   # tp1_dist * TP2_RATIO
    tp3=1429.0,   # rough tp3
    leverage=7,
    confidence=70.0,
):
    return Signal(
        symbol="TESTUSDT",
        direction=direction,
        entry_price=entry,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        sl=sl,
        leverage=leverage,
        risk_reward=2.08,
        confidence=confidence,
        btc_trend="Sideways",
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
        indicators={},
    )


# ── Leverage multiplier ─────────────────────────────────────────────────────

class TestLeveragedPnL:
    def test_tp1_profit_multiplied_by_leverage(self, monkeypatch):
        """TP1 realized PnL = risk_amount * (tp1_dist/sl_dist) * TP1_CLOSE_PCT * leverage."""
        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.0, raising=False)
        pm = PositionManager()
        sig = _make_signal(leverage=7)
        pos = pm.open_position(sig, equity=1000.0)

        sl_dist = abs(sig.sl - sig.entry_price) / sig.entry_price   # 0.10
        tp1_dist = abs(sig.tp1 - sig.entry_price) / sig.entry_price  # 0.10
        expected = pos.risk_amount * (tp1_dist / sl_dist) * config.TP1_CLOSE_PCT * 7

        pm.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})  # TP1 hit

        assert abs(pos.realized_pnl - expected) < 1e-9

    def test_sl_loss_multiplied_by_leverage(self, monkeypatch):
        """SL loss = risk_amount * leverage (full position, before TP1)."""
        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.0, raising=False)
        pm = PositionManager()
        sig = _make_signal(leverage=5)
        pos = pm.open_position(sig, equity=1000.0)

        expected_loss = pos.risk_amount * 5 * 1.0  # remaining_fraction = 1.0

        pm.update_positions({"TESTUSDT": (950.0, 850.0, 900.0)})  # SL hit

        assert abs(pos.realized_pnl - (-expected_loss)) < 1e-9

    def test_leverage_4x_gives_different_pnl_than_7x(self, monkeypatch):
        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.0, raising=False)
        pm4 = PositionManager()
        pm7 = PositionManager()
        pos4 = pm4.open_position(_make_signal(leverage=4), equity=1000.0)
        pos7 = pm7.open_position(_make_signal(leverage=7), equity=1000.0)

        pm4.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})
        pm7.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})

        assert pos7.realized_pnl > pos4.realized_pnl
        assert abs(pos7.realized_pnl / pos4.realized_pnl - 7 / 4) < 1e-9


# ── Fee deduction ────────────────────────────────────────────────────────────

class TestFeeDeduction:
    def test_fees_paid_nonzero_after_tp1(self):
        pm = PositionManager()
        pos = pm.open_position(_make_signal(), equity=1000.0)

        pm.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})

        assert pos.fees_paid > 0.0

    def test_fees_paid_nonzero_after_sl_hit(self):
        pm = PositionManager()
        pos = pm.open_position(_make_signal(), equity=1000.0)

        pm.update_positions({"TESTUSDT": (950.0, 850.0, 900.0)})

        assert pos.fees_paid > 0.0

    def test_fees_reduce_net_profit_vs_no_fees(self, monkeypatch):
        """Net profit with fees < gross profit without fees."""
        pm_no_fee = PositionManager()
        pm_with_fee = PositionManager()

        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.0, raising=False)
        pos_no_fee = pm_no_fee.open_position(_make_signal(), equity=1000.0)
        pm_no_fee.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})

        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.04, raising=False)
        pos_with_fee = pm_with_fee.open_position(_make_signal(), equity=1000.0)
        pm_with_fee.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})

        assert pos_with_fee.realized_pnl < pos_no_fee.realized_pnl

    def test_fees_accumulate_across_all_tp_levels(self):
        """fees_paid increases at each TP level."""
        pm = PositionManager()
        sig = _make_signal(
            tp1=1100.0,
            tp2=1261.0,
            tp3=1429.0,
        )
        pos = pm.open_position(sig, equity=1000.0)

        pm.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})
        fees_after_tp1 = pos.fees_paid

        pm.update_positions({"TESTUSDT": (1261.0, 1050.0, 1261.0)})
        fees_after_tp2 = pos.fees_paid

        pm.update_positions({"TESTUSDT": (1429.0, 1200.0, 1429.0)})
        fees_after_tp3 = pos.fees_paid

        assert fees_after_tp2 > fees_after_tp1
        assert fees_after_tp3 > fees_after_tp2

    def test_sl_breakeven_charges_fees_but_no_loss(self, monkeypatch):
        """After TP1, SL hit at breakeven: only fees deducted, no capital loss."""
        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.04, raising=False)
        pm = PositionManager()
        sig = _make_signal(leverage=7)
        pos = pm.open_position(sig, equity=1000.0)

        # Hit TP1
        pm.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})
        pnl_after_tp1 = pos.realized_pnl

        # SL hit at breakeven (entry price = 1000)
        pm.update_positions({"TESTUSDT": (1010.0, 950.0, 970.0)})

        # PnL decreased (fees paid) but no capital loss from SL
        assert pos.realized_pnl < pnl_after_tp1
        assert pos.fees_paid > 0.0
        # Entry was 1000, SL at 1000 = no loss from SL itself
        # Remaining 30% at breakeven, but fee was deducted
        expected_remaining = config.TP2_CLOSE_PCT + config.TP3_CLOSE_PCT  # 0.30
        expected_fee = (pos.risk_amount * 7) * expected_remaining * (0.04 / 100) * 2
        assert abs(pnl_after_tp1 - pos.realized_pnl - expected_fee) < 1e-9


# ── Position creation_at ────────────────────────────────────────────────────

class TestCreatedAt:
    def test_created_at_set_on_open(self):
        pm = PositionManager()
        pos = pm.open_position(_make_signal(), equity=1000.0)
        assert pos.created_at != ""
        # Should be a valid ISO datetime string
        datetime.fromisoformat(pos.created_at)

    def test_fees_paid_defaults_to_zero(self):
        pm = PositionManager()
        pos = pm.open_position(_make_signal(), equity=1000.0)
        assert pos.fees_paid == 0.0


# ── Trade log fields ─────────────────────────────────────────────────────────

class TestTradeLogFields:
    def test_log_trade_includes_required_fields(self, tmp_path):
        store = StateStore(db_path=str(tmp_path / "state.db"))
        trade_data = {
            "symbol": "TESTUSDT",
            "direction": "LONG",
            "event": "SL_HIT",
            "entry_price": 1000.0,
            "exit_price": 900.0,
            "leverage": 7,
            "confidence": 70.0,
            "risk_amount": 15.0,
            "realized_pnl": -105.42,
            "fees_paid": 0.42,
            "equity": 894.58,
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "opened_at": "2026-01-01T12:00:00",
            "closed_at": datetime.now().isoformat(),
            "timestamp": datetime.now().isoformat(),
        }
        store.log_trade("TestPassport", trade_data)

        import sqlite3
        with sqlite3.connect(str(tmp_path / "state.db")) as conn:
            row = conn.execute("SELECT trade_data_json FROM trade_log LIMIT 1").fetchone()

        parsed = json.loads(row[0])
        for field in ["symbol", "direction", "entry_price", "exit_price", "leverage",
                      "confidence", "risk_amount", "realized_pnl", "fees_paid",
                      "tp1_hit", "tp2_hit", "tp3_hit", "opened_at", "closed_at"]:
            assert field in parsed, f"Missing field: {field}"


# ── Equity snapshots v2 ──────────────────────────────────────────────────────

class TestEquitySnapshotsV2:
    def test_save_and_retrieve_equity_v2(self, tmp_path):
        store = StateStore(db_path=str(tmp_path / "state.db"))
        store.save_equity_v2("TestPassport", 500.0, 12.5, 2)
        rows = store.get_equity_history_v2("TestPassport")

        assert len(rows) == 1
        assert rows[0]["realized_equity"] == 500.0
        assert rows[0]["unrealized_pnl"] == 12.5
        assert rows[0]["total_equity"] == 512.5
        assert rows[0]["open_positions"] == 2

    def test_total_equity_is_sum_of_realized_plus_unrealized(self, tmp_path):
        store = StateStore(db_path=str(tmp_path / "state.db"))
        store.save_equity_v2("P1", 1000.0, -50.0, 1)
        rows = store.get_equity_history_v2("P1")
        assert rows[0]["total_equity"] == 950.0

    def test_get_equity_history_v2_respects_limit(self, tmp_path):
        store = StateStore(db_path=str(tmp_path / "state.db"))
        for i in range(10):
            store.save_equity_v2("P1", float(500 + i), 0.0, 0)
        rows = store.get_equity_history_v2("P1", limit=3)
        assert len(rows) == 3

    def test_get_equity_history_v2_filters_by_passport(self, tmp_path):
        store = StateStore(db_path=str(tmp_path / "state.db"))
        store.save_equity_v2("PassportA", 500.0, 0.0, 0)
        store.save_equity_v2("PassportB", 600.0, 5.0, 1)
        rows_a = store.get_equity_history_v2("PassportA")
        assert len(rows_a) == 1
        assert rows_a[0]["realized_equity"] == 500.0


# ── SL remaining fraction ────────────────────────────────────────────────────

class TestSLRemainingFraction:
    def test_sl_after_tp2_only_charges_10pct_fraction(self, monkeypatch):
        """After TP1+TP2 hit, SL at breakeven charges fees on only 10% remaining."""
        monkeypatch.setattr(config, "TRADING_FEE_PCT", 0.04, raising=False)
        pm = PositionManager()
        sig = _make_signal(leverage=7, tp1=1100.0, tp2=1261.0, tp3=1429.0)
        pos = pm.open_position(sig, equity=1000.0)

        pm.update_positions({"TESTUSDT": (1100.0, 990.0, 1100.0)})  # TP1
        pm.update_positions({"TESTUSDT": (1261.0, 1050.0, 1261.0)})  # TP2
        pnl_after_tp2 = pos.realized_pnl

        # SL at breakeven (1000) — only 10% remains
        pm.update_positions({"TESTUSDT": (1100.0, 950.0, 970.0)})

        expected_fee = (pos.risk_amount * 7) * config.TP3_CLOSE_PCT * (0.04 / 100) * 2
        assert abs(pnl_after_tp2 - pos.realized_pnl - expected_fee) < 1e-9

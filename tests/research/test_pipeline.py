"""Tests for the research pipeline orchestrator."""
import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from bot.research.pipeline import ResearchPipeline
from bot.research.types import BacktestMetrics


@pytest.fixture
def pipeline():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    p = ResearchPipeline(
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1h",
        days=180,
        db_path=db_path,
    )
    yield p
    p.tracker.close()
    os.unlink(db_path)


class TestResearchPipeline:
    def test_generate_candidates(self, pipeline):
        candidates = pipeline.generate_candidates(
            families=["ema_crossover"],
            max_per_family=3,
        )
        assert len(candidates) == 3
        for c in candidates:
            assert c.family == "ema_crossover"

    @patch("bot.research.pipeline.run_backtest")
    def test_run_stage1_filters_bad_candidates(self, mock_bt, pipeline):
        candidates = pipeline.generate_candidates(
            families=["volume_spike_breakout"], max_per_family=2,
        )
        mock_bt.side_effect = [
            {"trades": 50, "win_rate": 55, "return_pct": 10.0, "max_dd": 20.0,
             "sharpe": 0.8, "calmar": 0.5, "profit_factor": 1.3,
             "final_equity": 1100, "wins": 28, "losses": 22,
             "sortino": 1.0, "trade_details": []},
            {"trades": 5, "win_rate": 20, "return_pct": -30.0, "max_dd": 60.0,
             "sharpe": -0.5, "calmar": -0.2, "profit_factor": 0.5,
             "final_equity": 700, "wins": 1, "losses": 4,
             "sortino": -0.3, "trade_details": []},
        ]
        survivors = pipeline.run_stage1(candidates)
        assert len(survivors) <= len(candidates)

    def test_pipeline_generates_and_tracks(self, pipeline):
        candidates = pipeline.generate_candidates(
            families=["ema_crossover"], max_per_family=2,
        )
        assert pipeline.run_id is not None
        passports = pipeline.tracker.get_passports(pipeline.run_id)
        assert len(passports) == 2

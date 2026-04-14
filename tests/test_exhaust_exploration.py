"""Tests for the exhaustive exploration runner."""
import json
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from scripts.exhaust_exploration import (
    ExhaustiveExplorer,
    TierConfig,
    classify_families_from_db,
)


@pytest.fixture
def mock_research_db(tmp_path):
    """Create a minimal research DB with known family stats."""
    db_path = str(tmp_path / "research.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE passports (run_id TEXT, passport_id TEXT, slug TEXT, "
        "family TEXT, config_overrides TEXT, status TEXT)"
    )
    conn.execute(
        "CREATE TABLE eval_results (run_id TEXT, passport_id TEXT, stage INTEGER, "
        "passed INTEGER, metrics TEXT, reject_reason TEXT, secondary_reasons TEXT, evaluated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE experiments (run_id TEXT, total_generated INTEGER, "
        "stage1_survivors INTEGER, stage2_survivors INTEGER, status TEXT, "
        "started_at TEXT, finished_at TEXT)"
    )
    # Tier A family: 52 tested, 10 S2 survivors
    for i in range(52):
        pid = f"p_a_{i}"
        conn.execute(
            "INSERT INTO passports VALUES (?, ?, ?, ?, ?, ?)",
            ("r1", pid, f"slug_{i}", "tier_a_family", "{}", "generated"),
        )
        conn.execute(
            "INSERT INTO eval_results VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
            ("r1", pid, 1 if i < 30 else 0, "{}", None, None, None),
        )
        if i < 30:
            conn.execute(
                "INSERT INTO eval_results VALUES (?, ?, 2, ?, ?, ?, ?, ?)",
                ("r1", pid, 1 if i < 10 else 0, "{}", None, None, None),
            )
    # Tier C family: 52 tested, 0 S2 survivors
    for i in range(52):
        pid = f"p_c_{i}"
        conn.execute(
            "INSERT INTO passports VALUES (?, ?, ?, ?, ?, ?)",
            ("r1", pid, f"slug_{i}", "tier_c_family", "{}", "generated"),
        )
        conn.execute(
            "INSERT INTO eval_results VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
            ("r1", pid, 1 if i < 5 else 0, "{}", None, None, None),
        )
    conn.commit()
    conn.close()
    return db_path


class TestClassifyFamilies:
    def test_classify_tier_a(self, mock_research_db):
        families = classify_families_from_db(mock_research_db)
        assert families["tier_a_family"]["tier"] == "A"
        assert families["tier_a_family"]["s2_survivors"] == 10

    def test_classify_tier_c(self, mock_research_db):
        families = classify_families_from_db(mock_research_db)
        assert families["tier_c_family"]["tier"] == "C"
        assert families["tier_c_family"]["s2_survivors"] == 0


class TestTierConfig:
    def test_tier_a_full_grid(self):
        cfg = TierConfig.for_tier("A")
        assert cfg.full_grid is True
        assert cfg.max_per_family is None

    def test_tier_b_sampled(self):
        cfg = TierConfig.for_tier("B")
        assert cfg.full_grid is False
        assert cfg.max_per_family == 20

    def test_tier_c_last_chance(self):
        cfg = TierConfig.for_tier("C")
        assert cfg.full_grid is False
        assert cfg.max_per_family == 10
        assert cfg.last_chance is True


class TestExhaustiveExplorer:
    @patch("scripts.exhaust_exploration.ResearchPipeline")
    def test_init(self, mock_pipeline_cls, mock_research_db):
        explorer = ExhaustiveExplorer(
            db_path=mock_research_db,
            symbols=["BTCUSDT"],
            days=180,
        )
        assert explorer.db_path == mock_research_db

    @patch("scripts.exhaust_exploration.ResearchPipeline")
    def test_run_tier_c_last_chance(self, mock_pipeline_cls, mock_research_db):
        mock_pipeline = MagicMock()
        mock_pipeline.run_full.return_value = []
        mock_pipeline_cls.return_value = mock_pipeline

        explorer = ExhaustiveExplorer(
            db_path=mock_research_db,
            symbols=["BTCUSDT"],
            days=180,
        )
        results = explorer.run_tier("C", dry_run=True)
        assert "tier_c_family" in results

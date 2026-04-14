"""Tests for family verdict tracker."""
import os
import sqlite3
import tempfile

import pytest

from bot.research.verdict_tracker import VerdictTracker


@pytest.fixture
def tracker(tmp_path):
    db_path = str(tmp_path / "test_research.db")
    return VerdictTracker(db_path)


class TestVerdictTrackerInit:
    def test_creates_table(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='family_verdicts'"
        )
        assert cur.fetchone() is not None
        conn.close()

    def test_table_columns(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cur = conn.execute("PRAGMA table_info(family_verdicts)")
        cols = {row[1] for row in cur.fetchall()}
        expected = {
            "family", "tier", "total_tested", "s1_survivors", "s2_survivors",
            "s3_survivors", "s4_survivors", "last_chance_tested",
            "last_chance_s2", "verdict", "verdict_reason", "verdict_date",
            "updated_at",
        }
        assert expected.issubset(cols)
        conn.close()


class TestInitFromDB:
    def test_populates_from_research_db(self, tmp_path):
        db_path = str(tmp_path / "test_research.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE passports (run_id TEXT, passport_id TEXT, family TEXT, status TEXT)"
        )
        conn.execute(
            "CREATE TABLE eval_results (run_id TEXT, passport_id TEXT, stage INTEGER, passed INTEGER)"
        )
        conn.execute(
            "INSERT INTO passports VALUES ('r1', 'p1', 'rsi_momentum', 'generated')"
        )
        conn.execute(
            "INSERT INTO passports VALUES ('r1', 'p2', 'rsi_momentum', 'generated')"
        )
        conn.execute(
            "INSERT INTO eval_results VALUES ('r1', 'p1', 1, 1)"
        )
        conn.execute(
            "INSERT INTO eval_results VALUES ('r1', 'p1', 2, 1)"
        )
        conn.execute(
            "INSERT INTO eval_results VALUES ('r1', 'p2', 1, 1)"
        )
        conn.execute(
            "INSERT INTO eval_results VALUES ('r1', 'p2', 2, 0)"
        )
        conn.commit()
        conn.close()

        tracker = VerdictTracker(db_path)
        tracker.init_from_research_db()

        verdict = tracker.get_verdict("rsi_momentum")
        assert verdict["total_tested"] == 2
        assert verdict["s1_survivors"] == 2
        assert verdict["s2_survivors"] == 1


class TestTierClassification:
    def test_tier_a_threshold(self, tracker):
        tracker.upsert("strong_family", tier="A", total_tested=52, s2_survivors=7)
        v = tracker.get_verdict("strong_family")
        assert v["tier"] == "A"

    def test_tier_c_zero_survivors(self, tracker):
        tracker.upsert("dead_family", tier="C", total_tested=52, s2_survivors=0)
        v = tracker.get_verdict("dead_family")
        assert v["tier"] == "C"


class TestRetirement:
    def test_retire_family(self, tracker):
        tracker.upsert("dead_family", tier="C", total_tested=52, s2_survivors=0)
        tracker.retire("dead_family", reason="0/52 S2 survivors after last-chance round")
        v = tracker.get_verdict("dead_family")
        assert v["verdict"] == "retired"
        assert "last-chance" in v["verdict_reason"]
        assert v["verdict_date"] is not None

    def test_cannot_retire_exploring(self, tracker):
        tracker.upsert("active_family", tier="A", total_tested=10, s2_survivors=5)
        with pytest.raises(ValueError, match="still has S2 survivors"):
            tracker.retire("active_family", reason="premature")


class TestGetAllVerdicts:
    def test_list_all(self, tracker):
        tracker.upsert("fam_a", tier="A", total_tested=50, s2_survivors=10)
        tracker.upsert("fam_c", tier="C", total_tested=50, s2_survivors=0)
        all_v = tracker.get_all_verdicts()
        assert len(all_v) == 2

    def test_filter_by_tier(self, tracker):
        tracker.upsert("fam_a", tier="A", total_tested=50, s2_survivors=10)
        tracker.upsert("fam_c", tier="C", total_tested=50, s2_survivors=0)
        tier_c = tracker.get_all_verdicts(tier="C")
        assert len(tier_c) == 1
        assert tier_c[0]["family"] == "fam_c"

    def test_filter_by_verdict(self, tracker):
        tracker.upsert("fam_a", tier="A", total_tested=50, s2_survivors=10)
        tracker.upsert("fam_c", tier="C", total_tested=50, s2_survivors=0)
        tracker.retire("fam_c", reason="dead")
        retired = tracker.get_all_verdicts(verdict="retired")
        assert len(retired) == 1


class TestUpdateAfterRun:
    def test_increment_tested(self, tracker):
        tracker.upsert("fam", tier="B", total_tested=30, s2_survivors=2)
        tracker.update_after_run("fam", new_tested=10, new_s1=3, new_s2=1)
        v = tracker.get_verdict("fam")
        assert v["total_tested"] == 40
        assert v["s2_survivors"] == 3

    def test_last_chance_tracking(self, tracker):
        tracker.upsert("fam", tier="C", total_tested=50, s2_survivors=0)
        tracker.update_last_chance("fam", tested=10, s2=0)
        v = tracker.get_verdict("fam")
        assert v["last_chance_tested"] == 10
        assert v["last_chance_s2"] == 0

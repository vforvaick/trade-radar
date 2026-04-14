# Session 13 — Exhaustive Exploration & Go-to-Market Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exhaust all strategy family exploration with documented verdicts, then build go-to-market infrastructure (10-gate scorecard, kill switch, daily report) to prepare 3 passports for $100 real-money deployment.

**Architecture:** Extend the existing 4-stage research pipeline with a tier-based exploration runner that tracks family verdicts in SQLite. Build go-to-market infrastructure as new modules (circuit breaker, scorecard, daily report) integrated into the existing PassportRunner and TelegramNotifier.

**Tech Stack:** Python 3.12+, SQLite, existing bot/ modules, uv for package management

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `bot/research/verdict_tracker.py` | Family verdict CRUD — tracks tier, tested count, survivors, verdict status |
| `scripts/exhaust_exploration.py` | Tier-based exploration runner — orchestrates last-chance, grid completion, sampling |
| `bot/deploy/go_to_market.py` | 10-gate scorecard — evaluates passport readiness for real money |
| `bot/risk/circuit_breaker.py` | Kill switch — disables passport at 30% drawdown |
| `bot/reporting/daily_report.py` | Daily Telegram summary — all passport PnL, gate progress, alerts |
| `bot/reporting/__init__.py` | Package init |
| `docs/GO_TO_MARKET.md` | Deployment checklist and scorecard results |
| `tests/test_verdict_tracker.py` | Tests for verdict tracker |
| `tests/test_go_to_market.py` | Tests for scorecard |
| `tests/test_circuit_breaker.py` | Tests for kill switch |
| `tests/test_daily_report.py` | Tests for daily report |
| `tests/test_exhaust_exploration.py` | Tests for exploration runner |

### Modified Files
| File | Change |
|------|--------|
| `bot/passport_runner.py` | Integrate circuit breaker into `run_scan_cycle()` |
| `bot/research/tracker.py` | Add `family_verdicts` table creation to `__init__` |
| `run_research.py` | Add `--full-4stage` and `--tier` CLI options |
| `docs/FINDINGS.md` | Update with Session 13 family verdicts |
| `passports/VERSIONS.md` | Update with go-to-market candidates |

---

## Task 1: Family Verdict Tracker

**Files:**
- Create: `bot/research/verdict_tracker.py`
- Create: `tests/test_verdict_tracker.py`

- [ ] **Step 1: Write failing tests for VerdictTracker**

```python
# tests/test_verdict_tracker.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_verdict_tracker.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.research.verdict_tracker'`

- [ ] **Step 3: Implement VerdictTracker**

```python
# bot/research/verdict_tracker.py
"""Family verdict tracker — tracks exploration exhaustion per strategy family."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


class VerdictTracker:
    """Tracks exploration progress and retirement verdicts for strategy families."""

    def __init__(self, db_path: str = "research_experiments.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS family_verdicts (
                family TEXT PRIMARY KEY,
                tier TEXT NOT NULL DEFAULT 'C',
                total_tested INTEGER DEFAULT 0,
                s1_survivors INTEGER DEFAULT 0,
                s2_survivors INTEGER DEFAULT 0,
                s3_survivors INTEGER DEFAULT 0,
                s4_survivors INTEGER DEFAULT 0,
                last_chance_tested INTEGER DEFAULT 0,
                last_chance_s2 INTEGER DEFAULT 0,
                verdict TEXT DEFAULT 'exploring',
                verdict_reason TEXT,
                verdict_date TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

    def init_from_research_db(self) -> None:
        """Populate verdicts from existing passports and eval_results tables."""
        cur = self._conn.execute("""
            SELECT p.family,
                   COUNT(DISTINCT p.passport_id) as total_tested,
                   COUNT(DISTINCT CASE WHEN e1.passed = 1 THEN p.passport_id END) as s1_survivors,
                   COUNT(DISTINCT CASE WHEN e2.passed = 1 THEN p.passport_id END) as s2_survivors
            FROM passports p
            LEFT JOIN eval_results e1
                ON p.passport_id = e1.passport_id AND p.run_id = e1.run_id AND e1.stage = 1
            LEFT JOIN eval_results e2
                ON p.passport_id = e2.passport_id AND p.run_id = e2.run_id AND e2.stage = 2
            GROUP BY p.family
        """)
        for row in cur.fetchall():
            family = row[0]
            total = row[1]
            s1 = row[2]
            s2 = row[3]
            tier = self._classify_tier(s2, total)
            self.upsert(family, tier=tier, total_tested=total,
                        s1_survivors=s1, s2_survivors=s2)

    def _classify_tier(self, s2_survivors: int, total_tested: int) -> str:
        if s2_survivors >= 7:
            return "A"
        elif s2_survivors >= 1:
            return "B"
        else:
            return "C"

    def upsert(self, family: str, **kwargs) -> None:
        """Insert or update a family verdict row."""
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        existing = self.get_verdict(family)
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [family]
            self._conn.execute(
                f"UPDATE family_verdicts SET {sets} WHERE family = ?", vals
            )
        else:
            kwargs["family"] = family
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" for _ in kwargs)
            self._conn.execute(
                f"INSERT INTO family_verdicts ({cols}) VALUES ({placeholders})",
                list(kwargs.values()),
            )
        self._conn.commit()

    def get_verdict(self, family: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT * FROM family_verdicts WHERE family = ?", (family,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_all_verdicts(
        self, tier: Optional[str] = None, verdict: Optional[str] = None
    ) -> list[dict]:
        query = "SELECT * FROM family_verdicts WHERE 1=1"
        params: list = []
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        if verdict:
            query += " AND verdict = ?"
            params.append(verdict)
        query += " ORDER BY s2_survivors DESC, total_tested DESC"
        cur = self._conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def retire(self, family: str, reason: str) -> None:
        v = self.get_verdict(family)
        if not v:
            raise ValueError(f"Family '{family}' not found")
        if v["s2_survivors"] > 0 and v["last_chance_s2"] == 0:
            raise ValueError(
                f"Family '{family}' still has S2 survivors — cannot retire"
            )
        self.upsert(
            family,
            verdict="retired",
            verdict_reason=reason,
            verdict_date=datetime.now(timezone.utc).isoformat(),
        )

    def update_after_run(
        self, family: str, new_tested: int, new_s1: int, new_s2: int
    ) -> None:
        v = self.get_verdict(family)
        if not v:
            raise ValueError(f"Family '{family}' not found")
        self.upsert(
            family,
            total_tested=v["total_tested"] + new_tested,
            s1_survivors=v["s1_survivors"] + new_s1,
            s2_survivors=v["s2_survivors"] + new_s2,
        )

    def update_last_chance(self, family: str, tested: int, s2: int) -> None:
        self.upsert(family, last_chance_tested=tested, last_chance_s2=s2)

    def mark_exhausted(self, family: str) -> None:
        self.upsert(family, verdict="exhausted")

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_verdict_tracker.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add bot/research/verdict_tracker.py tests/test_verdict_tracker.py
git commit -m "feat: add family verdict tracker for exploration exhaustion

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Exploration Runner Script

**Files:**
- Create: `scripts/exhaust_exploration.py`
- Create: `tests/test_exhaust_exploration.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_exhaust_exploration.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_exhaust_exploration.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ExhaustiveExplorer**

```python
# scripts/exhaust_exploration.py
"""Exhaustive exploration runner — tier-based strategy family research.

Usage:
    uv run python scripts/exhaust_exploration.py --tier c --last-chance 10
    uv run python scripts/exhaust_exploration.py --tier a --full-grid
    uv run python scripts/exhaust_exploration.py --tier b --sample 20
    uv run python scripts/exhaust_exploration.py --all --days 180 --offline
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.research.families import SCORING_FAMILIES
from bot.research.pipeline import ResearchPipeline
from bot.research.verdict_tracker import VerdictTracker

logger = logging.getLogger(__name__)


@dataclass
class TierConfig:
    full_grid: bool = False
    max_per_family: Optional[int] = None
    last_chance: bool = False
    run_stage3: bool = False
    run_stage4: bool = False

    @classmethod
    def for_tier(cls, tier: str) -> "TierConfig":
        if tier == "A":
            return cls(full_grid=True, max_per_family=None, run_stage3=True, run_stage4=True)
        elif tier == "B":
            return cls(full_grid=False, max_per_family=20)
        elif tier == "C":
            return cls(full_grid=False, max_per_family=10, last_chance=True)
        else:
            raise ValueError(f"Unknown tier: {tier}")


def classify_families_from_db(db_path: str) -> dict[str, dict]:
    """Classify all families into tiers based on research DB stats."""
    tracker = VerdictTracker(db_path)
    tracker.init_from_research_db()
    verdicts = tracker.get_all_verdicts()
    tracker.close()
    return {v["family"]: v for v in verdicts}


class ExhaustiveExplorer:
    """Orchestrates tier-based exhaustive exploration of strategy families."""

    def __init__(
        self,
        db_path: str = "research_experiments.db",
        symbols: Optional[list[str]] = None,
        days: int = 180,
        interval: str = "1h",
        offline: bool = False,
    ):
        self.db_path = db_path
        self.symbols = symbols or []
        self.days = days
        self.interval = interval
        self.offline = offline
        self.verdict_tracker = VerdictTracker(db_path)
        self.verdict_tracker.init_from_research_db()

    def run_tier(self, tier: str, dry_run: bool = False) -> dict[str, dict]:
        """Run exploration for all families in a given tier."""
        cfg = TierConfig.for_tier(tier)
        families = self.verdict_tracker.get_all_verdicts(tier=tier)

        # Skip already retired families
        active = [f for f in families if f["verdict"] != "retired"]
        results = {}

        for fam_data in active:
            family_name = fam_data["family"]
            if family_name not in SCORING_FAMILIES:
                logger.warning("Family %s not in SCORING_FAMILIES, skipping", family_name)
                results[family_name] = {"skipped": True, "reason": "not in SCORING_FAMILIES"}
                continue

            if dry_run:
                results[family_name] = {
                    "dry_run": True,
                    "tier": tier,
                    "would_test": cfg.max_per_family or "full grid",
                }
                continue

            logger.info(
                "Running %s exploration for %s (tier %s, tested=%d, s2=%d)",
                "last-chance" if cfg.last_chance else "grid",
                family_name, tier, fam_data["total_tested"], fam_data["s2_survivors"],
            )

            pipeline = ResearchPipeline(
                symbols=self.symbols,
                interval=self.interval,
                days=self.days,
                db_path=self.db_path,
            )

            if cfg.run_stage3 and cfg.run_stage4:
                result = pipeline.run_full_4stage(
                    families=[family_name],
                    max_per_family=cfg.max_per_family,
                    offline=self.offline,
                )
                new_s2 = len(result.selected_passport_ids) if result else 0
            else:
                survivors = pipeline.run_full(
                    families=[family_name],
                    max_per_family=cfg.max_per_family,
                    offline=self.offline,
                )
                new_s2 = len(survivors)

            tested_count = cfg.max_per_family or len(
                SCORING_FAMILIES[family_name].get("param_ranges", {})
            )

            if cfg.last_chance:
                self.verdict_tracker.update_last_chance(family_name, tested=tested_count, s2=new_s2)
                if new_s2 == 0:
                    self.verdict_tracker.retire(
                        family_name,
                        reason=f"0/{fam_data['total_tested'] + tested_count} S2 survivors "
                               f"after last-chance round ({tested_count} extra combos)",
                    )
                    logger.info("RETIRED: %s — no survivors after last-chance", family_name)
                else:
                    logger.info(
                        "PROMOTED: %s — %d new S2 survivors from last-chance, upgrading to Tier B",
                        family_name, new_s2,
                    )
                    self.verdict_tracker.upsert(family_name, tier="B")
            else:
                self.verdict_tracker.update_after_run(family_name, tested_count, 0, new_s2)

            results[family_name] = {
                "tier": tier,
                "new_tested": tested_count,
                "new_s2": new_s2,
                "verdict": self.verdict_tracker.get_verdict(family_name)["verdict"],
            }

        return results

    def run_all_tiers(self, dry_run: bool = False) -> dict:
        """Run exploration across all tiers in sequence: C → B → A."""
        all_results = {}
        for tier in ["C", "B", "A"]:
            logger.info("=== Running Tier %s exploration ===", tier)
            tier_results = self.run_tier(tier, dry_run=dry_run)
            all_results[tier] = tier_results
        return all_results

    def print_summary(self) -> None:
        """Print current family verdict summary."""
        verdicts = self.verdict_tracker.get_all_verdicts()
        print("\n" + "=" * 70)
        print("FAMILY EXPLORATION STATUS")
        print("=" * 70)
        for tier in ["A", "B", "C"]:
            tier_fams = [v for v in verdicts if v["tier"] == tier]
            if not tier_fams:
                continue
            print(f"\n--- Tier {tier} ---")
            for v in tier_fams:
                status = "🔴 RETIRED" if v["verdict"] == "retired" else \
                         "🟡 EXHAUSTED" if v["verdict"] == "exhausted" else "🟢 EXPLORING"
                print(
                    f"  {v['family']:30s} | tested={v['total_tested']:4d} | "
                    f"S1={v['s1_survivors']:3d} | S2={v['s2_survivors']:3d} | {status}"
                )
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Exhaustive strategy exploration runner")
    parser.add_argument("--tier", choices=["A", "B", "C", "all"], default="all")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--pairs", type=int, default=15)
    parser.add_argument("--db-path", type=str, default="research_experiments.db")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--summary", action="store_true", help="Print current status only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.summary:
        explorer = ExhaustiveExplorer(db_path=args.db_path)
        explorer.print_summary()
        return

    from bot.research.data_cache import KlineCache
    cache = KlineCache()
    symbols = cache.available_symbols()[:args.pairs] if args.offline else []

    if not args.offline:
        from bot.data_fetcher import get_top_volume_symbols
        symbols = get_top_volume_symbols(limit=args.pairs)

    explorer = ExhaustiveExplorer(
        db_path=args.db_path,
        symbols=symbols,
        days=args.days,
        offline=args.offline,
    )

    if args.tier == "all":
        results = explorer.run_all_tiers(dry_run=args.dry_run)
    else:
        results = explorer.run_tier(args.tier, dry_run=args.dry_run)

    explorer.print_summary()
    logger.info("Exploration complete. Results: %s", results)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_exhaust_exploration.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/exhaust_exploration.py tests/test_exhaust_exploration.py
git commit -m "feat: add exhaustive exploration runner with tier-based pipeline

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Go-to-Market Scorecard

**Files:**
- Create: `bot/deploy/go_to_market.py`
- Create: `tests/test_go_to_market.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_go_to_market.py
"""Tests for go-to-market 10-gate scorecard."""
import pytest

from bot.deploy.go_to_market import GoToMarketScorecard, GateResult, ScorecardResult


class TestGateResult:
    def test_pass(self):
        r = GateResult(gate="gate_1_return", passed=True, value=18.5, threshold=15.0)
        assert r.passed is True

    def test_fail(self):
        r = GateResult(gate="gate_1_return", passed=False, value=10.0, threshold=15.0)
        assert r.passed is False


class TestScorecardResult:
    def test_all_pass(self):
        gates = [
            GateResult("g1", True, 20, 15),
            GateResult("g2", True, 1.5, 1.3),
        ]
        result = ScorecardResult(passport_name="Test", gates=gates)
        assert result.all_passed is True
        assert result.passed_count == 2
        assert result.total_count == 2

    def test_partial_pass(self):
        gates = [
            GateResult("g1", True, 20, 15),
            GateResult("g2", False, 1.1, 1.3),
        ]
        result = ScorecardResult(passport_name="Test", gates=gates)
        assert result.all_passed is False
        assert result.passed_count == 1


class TestGoToMarketScorecard:
    def test_backtest_gates_pass(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 18.5,
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 35,
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        assert result.all_passed is True
        assert result.passed_count == 10

    def test_backtest_gates_fail_return(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 10.0,  # below 15%
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 35,
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        assert result.all_passed is False
        assert result.passed_count == 9
        failed = [g for g in result.gates if not g.passed]
        assert failed[0].gate == "gate_1_return"

    def test_paper_gates_fail_days(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 20.0,
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 20,  # below 30
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        assert result.all_passed is False
        failed = [g for g in result.gates if not g.passed]
        assert any(g.gate == "gate_8_paper_days" for g in failed)

    def test_missing_metric_raises(self):
        sc = GoToMarketScorecard()
        with pytest.raises(KeyError):
            sc.evaluate("TestPassport", {"return_pct_180d": 20.0})

    def test_format_table(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 18.5,
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 35,
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        table = result.format_table()
        assert "TestPassport" in table
        assert "✅" in table
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_go_to_market.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GoToMarketScorecard**

```python
# bot/deploy/go_to_market.py
"""Go-to-market 10-gate scorecard for real-money deployment readiness."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GateResult:
    gate: str
    passed: bool
    value: float
    threshold: float
    description: str = ""


@dataclass
class ScorecardResult:
    passport_name: str
    gates: list[GateResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    @property
    def total_count(self) -> int:
        return len(self.gates)

    def format_table(self) -> str:
        lines = [
            f"📋 Go-to-Market Scorecard: {self.passport_name}",
            f"   Result: {'✅ PASS' if self.all_passed else '❌ FAIL'} "
            f"({self.passed_count}/{self.total_count} gates)",
            "",
        ]
        for g in self.gates:
            icon = "✅" if g.passed else "❌"
            lines.append(
                f"   {icon} {g.gate:30s} | value={g.value:.2f} | "
                f"threshold={g.threshold:.2f} | {g.description}"
            )
        return "\n".join(lines)


GATE_DEFINITIONS = [
    {
        "name": "gate_1_return",
        "description": "180d return > 15%",
        "metric": "return_pct_180d",
        "threshold": 15.0,
        "comparator": "gt",
    },
    {
        "name": "gate_2_profit_factor",
        "description": "Profit factor > 1.3",
        "metric": "profit_factor",
        "threshold": 1.3,
        "comparator": "gt",
    },
    {
        "name": "gate_3_max_drawdown",
        "description": "Max drawdown < 40%",
        "metric": "max_drawdown",
        "threshold": 40.0,
        "comparator": "lt",
    },
    {
        "name": "gate_4_min_trades",
        "description": "Min 50 trades",
        "metric": "total_trades",
        "threshold": 50.0,
        "comparator": "gte",
    },
    {
        "name": "gate_5_win_rate",
        "description": "Win rate > 35%",
        "metric": "win_rate",
        "threshold": 35.0,
        "comparator": "gt",
    },
    {
        "name": "gate_6_mc_robust",
        "description": "Monte Carlo 70%+ profitable",
        "metric": "mc_profitable_pct",
        "threshold": 70.0,
        "comparator": "gte",
    },
    {
        "name": "gate_7_orthogonal",
        "description": "Orthogonality rank = 1",
        "metric": "correlation_group_rank",
        "threshold": 1.0,
        "comparator": "eq",
    },
    {
        "name": "gate_8_paper_days",
        "description": "30+ days paper trading",
        "metric": "paper_days",
        "threshold": 30.0,
        "comparator": "gte",
    },
    {
        "name": "gate_9_paper_pnl",
        "description": "Paper PnL positive",
        "metric": "paper_pnl",
        "threshold": 0.0,
        "comparator": "gt",
    },
    {
        "name": "gate_10_no_catastrophe",
        "description": "No single trade loss > 10% equity",
        "metric": "max_single_loss_pct",
        "threshold": 10.0,
        "comparator": "lt",
    },
]


class GoToMarketScorecard:
    """Evaluates passport readiness for real-money deployment."""

    def __init__(self, gate_overrides: Optional[dict] = None):
        self.gates = GATE_DEFINITIONS.copy()
        if gate_overrides:
            for gate in self.gates:
                if gate["name"] in gate_overrides:
                    gate["threshold"] = gate_overrides[gate["name"]]

    def evaluate(self, passport_name: str, metrics: dict) -> ScorecardResult:
        results = []
        for gate in self.gates:
            value = metrics[gate["metric"]]
            threshold = gate["threshold"]
            comparator = gate["comparator"]

            if comparator == "gt":
                passed = value > threshold
            elif comparator == "gte":
                passed = value >= threshold
            elif comparator == "lt":
                passed = value < threshold
            elif comparator == "lte":
                passed = value <= threshold
            elif comparator == "eq":
                passed = value == threshold
            else:
                passed = False

            results.append(GateResult(
                gate=gate["name"],
                passed=passed,
                value=float(value),
                threshold=float(threshold),
                description=gate["description"],
            ))

        return ScorecardResult(passport_name=passport_name, gates=results)

    def evaluate_from_db(
        self,
        passport_name: str,
        research_db_path: str = "research_experiments.db",
        state_db_path: str = "state.db",
    ) -> ScorecardResult:
        """Build metrics from research DB + paper state DB, then evaluate."""
        import sqlite3
        from datetime import datetime, timezone

        metrics = {}

        # Backtest metrics from research DB
        conn = sqlite3.connect(research_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT e.metrics FROM eval_results e
            JOIN passports p ON e.passport_id = p.passport_id AND e.run_id = p.run_id
            WHERE p.slug LIKE ? AND e.stage = 2 AND e.passed = 1
            ORDER BY e.evaluated_at DESC LIMIT 1
        """, (f"%{passport_name}%",))
        row = cur.fetchone()
        if row:
            bt_metrics = json.loads(row["metrics"])
            metrics["return_pct_180d"] = bt_metrics.get("median_return", 0) * 100
            metrics["profit_factor"] = bt_metrics.get("avg_profit_factor", 0)
            metrics["max_drawdown"] = bt_metrics.get("max_fold_dd", 100)
            metrics["total_trades"] = bt_metrics.get("total_trades", 0)
            metrics["win_rate"] = bt_metrics.get("win_rate", 0)
        else:
            metrics.update({
                "return_pct_180d": 0, "profit_factor": 0,
                "max_drawdown": 100, "total_trades": 0, "win_rate": 0,
            })
        conn.close()

        # MC and orthogonality (default to not-yet-tested)
        metrics.setdefault("mc_profitable_pct", 0)
        metrics.setdefault("correlation_group_rank", 99)

        # Paper trading metrics from state DB
        state_conn = sqlite3.connect(state_db_path)
        state_conn.row_factory = sqlite3.Row

        cur = state_conn.execute("""
            SELECT MIN(timestamp) as first, MAX(timestamp) as last
            FROM equity_snapshots WHERE passport_name = ?
        """, (passport_name,))
        row = cur.fetchone()
        if row and row["first"]:
            first = datetime.fromisoformat(row["first"])
            last = datetime.fromisoformat(row["last"])
            metrics["paper_days"] = (last - first).days
        else:
            metrics["paper_days"] = 0

        cur = state_conn.execute("""
            SELECT equity FROM equity_snapshots
            WHERE passport_name = ? ORDER BY timestamp DESC LIMIT 1
        """, (passport_name,))
        row = cur.fetchone()
        from bot import config
        initial = getattr(config, "INITIAL_EQUITY", 500)
        metrics["paper_pnl"] = (row["equity"] - initial) if row else 0

        cur = state_conn.execute("""
            SELECT MIN(realized_pnl) as worst_loss, equity_at_entry
            FROM positions WHERE passport_name = ? AND status != 'OPEN'
        """, (passport_name,))
        row = cur.fetchone()
        if row and row["worst_loss"] is not None and row["equity_at_entry"]:
            metrics["max_single_loss_pct"] = abs(row["worst_loss"]) / row["equity_at_entry"] * 100
        else:
            metrics["max_single_loss_pct"] = 0

        state_conn.close()

        return self.evaluate(passport_name, metrics)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_go_to_market.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add bot/deploy/go_to_market.py tests/test_go_to_market.py
git commit -m "feat: add go-to-market 10-gate scorecard

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Circuit Breaker (Kill Switch)

**Files:**
- Create: `bot/risk/circuit_breaker.py`
- Create: `tests/test_circuit_breaker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_circuit_breaker.py
"""Tests for circuit breaker (kill switch)."""
from unittest.mock import MagicMock, patch

import pytest

from bot.risk.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_no_trigger_above_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=400, initial_equity=500) is False

    def test_trigger_at_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=350, initial_equity=500) is True

    def test_trigger_below_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=300, initial_equity=500) is True

    def test_custom_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.50)
        assert cb.should_kill("TestPassport", current_equity=260, initial_equity=500) is False
        assert cb.should_kill("TestPassport", current_equity=250, initial_equity=500) is True

    def test_zero_initial_equity_no_crash(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=0, initial_equity=0) is False

    def test_per_passport_override(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        # 20% drawdown with 50% threshold = should NOT kill
        assert cb.should_kill(
            "TestPassport", current_equity=80, initial_equity=100,
            override_threshold=0.50,
        ) is False
        # 20% drawdown with 10% threshold = should kill
        assert cb.should_kill(
            "TestPassport", current_equity=80, initial_equity=100,
            override_threshold=0.10,
        ) is True


class TestCircuitBreakerLog:
    def test_kill_event_logged(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        cb.should_kill("TestPassport", current_equity=300, initial_equity=500)
        assert len(cb.kill_log) == 1
        assert cb.kill_log[0]["passport"] == "TestPassport"
        assert cb.kill_log[0]["equity"] == 300

    def test_no_duplicate_kill_log(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        cb.should_kill("TestPassport", current_equity=300, initial_equity=500)
        cb.should_kill("TestPassport", current_equity=280, initial_equity=500)
        assert len(cb.kill_log) == 1  # only first trigger logged

    def test_different_passports_logged_separately(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        cb.should_kill("Passport1", current_equity=300, initial_equity=500)
        cb.should_kill("Passport2", current_equity=300, initial_equity=500)
        assert len(cb.kill_log) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_circuit_breaker.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CircuitBreaker**

```python
# bot/risk/circuit_breaker.py
"""Circuit breaker — kills passport trading when drawdown exceeds threshold."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Disables passport trading when equity drawdown exceeds threshold.

    Default threshold: 30% drawdown from initial equity.
    Per-passport override via config_overrides.KILL_SWITCH_THRESHOLD.
    """

    def __init__(self, kill_threshold_pct: float = 0.30):
        self.kill_threshold_pct = kill_threshold_pct
        self.kill_log: list[dict] = []
        self._killed_passports: set[str] = set()

    def should_kill(
        self,
        passport_name: str,
        current_equity: float,
        initial_equity: float,
        override_threshold: Optional[float] = None,
    ) -> bool:
        """Check if passport should be killed due to drawdown.

        Returns True if drawdown >= threshold. Logs kill event on first trigger.
        """
        if initial_equity <= 0:
            return False

        threshold = override_threshold or self.kill_threshold_pct
        drawdown = (initial_equity - current_equity) / initial_equity

        if drawdown >= threshold:
            if passport_name not in self._killed_passports:
                self._killed_passports.add(passport_name)
                event = {
                    "passport": passport_name,
                    "equity": current_equity,
                    "initial_equity": initial_equity,
                    "drawdown_pct": round(drawdown * 100, 2),
                    "threshold_pct": round(threshold * 100, 2),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.kill_log.append(event)
                logger.warning(
                    "🔴 KILL SWITCH: %s — equity $%.2f (%.1f%% drawdown, threshold %.0f%%)",
                    passport_name, current_equity, drawdown * 100, threshold * 100,
                )
            return True

        return False

    def is_killed(self, passport_name: str) -> bool:
        return passport_name in self._killed_passports

    def reset(self, passport_name: str) -> None:
        self._killed_passports.discard(passport_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_circuit_breaker.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add bot/risk/circuit_breaker.py tests/test_circuit_breaker.py
git commit -m "feat: add circuit breaker kill switch for drawdown protection

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Integrate Circuit Breaker into PassportRunner

**Files:**
- Modify: `bot/passport_runner.py` (in `run_scan_cycle` method)
- Create: `tests/test_circuit_breaker_integration.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_circuit_breaker_integration.py
"""Integration tests for circuit breaker in PassportRunner."""
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from bot.risk.circuit_breaker import CircuitBreaker


class TestCircuitBreakerInRunner:
    """Test that PassportRunner respects circuit breaker."""

    def test_passport_skipped_when_killed(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        # Simulate killed passport
        killed = cb.should_kill("TestPassport", current_equity=300, initial_equity=500)
        assert killed is True
        assert cb.is_killed("TestPassport") is True

    def test_passport_not_skipped_when_healthy(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        killed = cb.should_kill("TestPassport", current_equity=400, initial_equity=500)
        assert killed is False
        assert cb.is_killed("TestPassport") is False

    def test_per_passport_threshold_from_config(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        # Passport with custom 50% threshold
        killed = cb.should_kill(
            "HighRisk",
            current_equity=60,
            initial_equity=100,
            override_threshold=0.50,
        )
        assert killed is False  # 40% < 50%

        killed = cb.should_kill(
            "HighRisk",
            current_equity=49,
            initial_equity=100,
            override_threshold=0.50,
        )
        assert killed is True  # 51% >= 50%
```

- [ ] **Step 2: Run tests to verify they pass** (these test the CB directly, integration is next)

Run: `uv run pytest tests/test_circuit_breaker_integration.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 3: Add CircuitBreaker to PassportRunner**

In `bot/passport_runner.py`, add the circuit breaker import and initialization:

At the top of the file, add import:
```python
from bot.risk.circuit_breaker import CircuitBreaker
```

In `PassportRunner.__init__`, add after `self.regime_logger`:
```python
self.circuit_breaker = CircuitBreaker(
    kill_threshold_pct=getattr(config, "KILL_SWITCH_THRESHOLD", 0.30)
)
```

In `run_scan_cycle()`, BEFORE the regime gate check (the `if passport.active_regimes` block), add:
```python
# Circuit breaker check
override_threshold = passport.config_overrides.get("KILL_SWITCH_THRESHOLD")
if self.circuit_breaker.should_kill(
    passport.name,
    current_equity=passport.equity,
    initial_equity=getattr(config, "INITIAL_EQUITY", 500),
    override_threshold=override_threshold,
):
    logger.warning(
        "⛔ %s %s KILLED by circuit breaker (equity $%.2f)",
        passport.emoji, passport.name, passport.equity,
    )
    if self.notifier:
        self.notifier.send_error(
            f"⛔ KILL SWITCH: {passport.emoji} {passport.name}\n"
            f"Equity: ${passport.equity:.2f}\n"
            f"Drawdown: {((getattr(config, 'INITIAL_EQUITY', 500) - passport.equity) / getattr(config, 'INITIAL_EQUITY', 500) * 100):.1f}%\n"
            f"Trading DISABLED for this passport."
        )
    continue
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --tb=short -q`
Expected: All existing tests PASS (889+), no regressions

- [ ] **Step 5: Commit**

```bash
git add bot/passport_runner.py tests/test_circuit_breaker_integration.py
git commit -m "feat: integrate circuit breaker into PassportRunner scan cycle

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Daily Telegram Report

**Files:**
- Create: `bot/reporting/__init__.py`
- Create: `bot/reporting/daily_report.py`
- Create: `tests/test_daily_report.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_daily_report.py
"""Tests for daily Telegram report."""
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from bot.reporting.daily_report import DailyReportBuilder


@pytest.fixture
def mock_state_db(tmp_path):
    db_path = str(tmp_path / "state.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE equity_snapshots (
            id INTEGER PRIMARY KEY, passport_name TEXT,
            equity REAL, timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY, passport_name TEXT, symbol TEXT,
            signal_json TEXT, status TEXT, risk_amount REAL,
            equity_at_entry REAL, tp1_hit INTEGER DEFAULT 0,
            tp2_hit INTEGER DEFAULT 0, tp3_hit INTEGER DEFAULT 0,
            sl_is_breakeven INTEGER DEFAULT 0, realized_pnl REAL DEFAULT 0,
            trailing_sl REAL, tg_msg_id TEXT, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY, passport_name TEXT,
            trade_data_json TEXT, timestamp TEXT
        )
    """)
    now = datetime.now(timezone.utc).isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn.executemany(
        "INSERT INTO equity_snapshots (passport_name, equity, timestamp) VALUES (?, ?, ?)",
        [
            ("PassportA", 520.0, now),
            ("PassportA", 500.0, yesterday),
            ("PassportB", 480.0, now),
            ("PassportB", 500.0, yesterday),
        ],
    )
    conn.executemany(
        "INSERT INTO positions (passport_name, symbol, status, realized_pnl, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("PassportA", "BTCUSDT", "TP1", 15.0, now),
            ("PassportA", "ETHUSDT", "SL_HIT", -8.0, now),
            ("PassportB", "SOLUSDT", "OPEN", 0.0, now),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


class TestDailyReportBuilder:
    def test_build_report_text(self, mock_state_db):
        builder = DailyReportBuilder(state_db_path=mock_state_db, initial_equity=500.0)
        report = builder.build()
        assert "PassportA" in report
        assert "PassportB" in report
        assert "Daily Report" in report

    def test_passport_pnl_calculated(self, mock_state_db):
        builder = DailyReportBuilder(state_db_path=mock_state_db, initial_equity=500.0)
        data = builder.get_passport_summaries()
        assert len(data) == 2
        a_data = next(d for d in data if d["name"] == "PassportA")
        assert a_data["current_equity"] == 520.0
        assert a_data["pnl_pct"] == pytest.approx(4.0, rel=0.1)

    def test_empty_db(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE equity_snapshots (id INTEGER PRIMARY KEY, passport_name TEXT, equity REAL, timestamp TEXT)"
        )
        conn.execute(
            "CREATE TABLE positions (id INTEGER PRIMARY KEY, passport_name TEXT, symbol TEXT, status TEXT, realized_pnl REAL, created_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE trade_log (id INTEGER PRIMARY KEY, passport_name TEXT, trade_data_json TEXT, timestamp TEXT)"
        )
        conn.commit()
        conn.close()
        builder = DailyReportBuilder(state_db_path=db_path, initial_equity=500.0)
        report = builder.build()
        assert "No passport data" in report or "Daily Report" in report

    def test_report_sorted_by_pnl(self, mock_state_db):
        builder = DailyReportBuilder(state_db_path=mock_state_db, initial_equity=500.0)
        data = builder.get_passport_summaries()
        # PassportA (+4%) should come before PassportB (-4%)
        assert data[0]["name"] == "PassportA"
        assert data[1]["name"] == "PassportB"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daily_report.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create package init**

```python
# bot/reporting/__init__.py
```

- [ ] **Step 4: Implement DailyReportBuilder**

```python
# bot/reporting/daily_report.py
"""Daily Telegram performance report for all passports."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class DailyReportBuilder:
    """Builds daily performance summary for all passports."""

    def __init__(
        self,
        state_db_path: str = "state.db",
        initial_equity: float = 500.0,
    ):
        self.state_db_path = state_db_path
        self.initial_equity = initial_equity

    def get_passport_summaries(self) -> list[dict]:
        conn = sqlite3.connect(self.state_db_path)
        conn.row_factory = sqlite3.Row

        cur = conn.execute("""
            SELECT passport_name,
                   equity as current_equity,
                   timestamp
            FROM equity_snapshots e1
            WHERE timestamp = (
                SELECT MAX(timestamp) FROM equity_snapshots e2
                WHERE e2.passport_name = e1.passport_name
            )
            GROUP BY passport_name
        """)
        snapshots = {row["passport_name"]: dict(row) for row in cur.fetchall()}

        cur = conn.execute("""
            SELECT passport_name,
                   COUNT(*) as total_trades,
                   SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                   COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_positions
            FROM positions
            GROUP BY passport_name
        """)
        trade_stats = {row["passport_name"]: dict(row) for row in cur.fetchall()}
        conn.close()

        summaries = []
        for name, snap in snapshots.items():
            equity = snap["current_equity"]
            pnl_pct = ((equity - self.initial_equity) / self.initial_equity) * 100
            stats = trade_stats.get(name, {})
            total = stats.get("total_trades", 0)
            wins = stats.get("wins", 0)
            wr = (wins / total * 100) if total > 0 else 0

            summaries.append({
                "name": name,
                "current_equity": equity,
                "pnl_pct": round(pnl_pct, 2),
                "total_trades": total,
                "win_rate": round(wr, 1),
                "open_positions": stats.get("open_positions", 0),
            })

        summaries.sort(key=lambda x: x["pnl_pct"], reverse=True)
        return summaries

    def build(self) -> str:
        summaries = self.get_passport_summaries()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"📊 Cryptopass Daily Report — {now}",
            "",
        ]

        if not summaries:
            lines.append("No passport data available.")
            return "\n".join(lines)

        total_equity = sum(s["current_equity"] for s in summaries)
        total_initial = self.initial_equity * len(summaries)
        total_pnl_pct = ((total_equity - total_initial) / total_initial) * 100 if total_initial > 0 else 0

        lines.append(
            f"💰 Total: ${total_equity:,.2f} / ${total_initial:,.2f} ({total_pnl_pct:+.1f}%)"
        )
        lines.append("")

        # Top performers
        lines.append("=== TOP PERFORMERS ===")
        for s in summaries[:10]:
            icon = "🔥" if s["pnl_pct"] > 10 else "📈" if s["pnl_pct"] > 0 else "📉"
            lines.append(
                f"{icon} {s['name']}: {s['pnl_pct']:+.1f}% | "
                f"{s['total_trades']}t WR={s['win_rate']:.0f}% | "
                f"{s['open_positions']} open"
            )

        # Worst performers
        worst = [s for s in summaries if s["pnl_pct"] < -10]
        if worst:
            lines.append("")
            lines.append("=== NEEDS ATTENTION ===")
            for s in worst[-5:]:
                lines.append(
                    f"⚠️ {s['name']}: {s['pnl_pct']:+.1f}% | "
                    f"{s['total_trades']}t WR={s['win_rate']:.0f}%"
                )

        return "\n".join(lines)

    def send_via_telegram(self, notifier) -> None:
        report = self.build()
        notifier.send_update(report)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_daily_report.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add bot/reporting/__init__.py bot/reporting/daily_report.py tests/test_daily_report.py
git commit -m "feat: add daily Telegram performance report

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Add --full-4stage to run_research.py CLI

**Files:**
- Modify: `run_research.py`

- [ ] **Step 1: Check current CLI args**

Run: `uv run python run_research.py --help`

- [ ] **Step 2: Add --full-4stage flag**

In `run_research.py`, add to the argument parser:
```python
parser.add_argument(
    "--full-4stage", action="store_true",
    help="Run full 4-stage pipeline (S1→S2→S3→S4) instead of 2-stage",
)
```

In the main execution section, replace the pipeline call:
```python
if args.full_4stage:
    logger.info("Running full 4-stage pipeline (S1→S2→S3→S4)...")
    result = pipeline.run_full_4stage(
        families=families,
        max_per_family=args.max_per_family,
        mc_iterations=50,
        offline=args.offline,
    )
    if result:
        logger.info("Stage 4 result: %d selected, portfolio Sharpe=%.2f",
                     len(result.selected_passport_ids), result.portfolio_sharpe)
else:
    survivors = pipeline.run_full(
        families=families,
        max_per_family=args.max_per_family,
        offline=args.offline,
    )
```

- [ ] **Step 3: Verify CLI works**

Run: `uv run python run_research.py --help`
Expected: `--full-4stage` appears in help output

- [ ] **Step 4: Commit**

```bash
git add run_research.py
git commit -m "feat: add --full-4stage flag to run_research.py CLI

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: GO_TO_MARKET.md Documentation

**Files:**
- Create: `docs/GO_TO_MARKET.md`

- [ ] **Step 1: Create the go-to-market documentation**

```markdown
# Go-to-Market: Real Money Deployment Guide

## Overview

This document tracks passport readiness for real-money deployment on Binance Futures.

## The 10 Gates

Every passport must pass ALL 10 gates before receiving real money.

### Backtest Gates (Research Pipeline)
| Gate | Metric | Threshold | Source |
|------|--------|-----------|--------|
| 1 | 180d Return | > 15% | `run_research.py --full-4stage` |
| 2 | Profit Factor | > 1.3 | Stage 1 evaluator |
| 3 | Max Drawdown | < 40% | Stage 1 evaluator |
| 4 | Min Trades | ≥ 50 | Stage 1 evaluator |
| 5 | Win Rate | > 35% | Stage 1 evaluator |
| 6 | MC Robustness | ≥ 70% profitable | Stage 3 evaluator |
| 7 | Orthogonality | Rank 1 in group | Stage 4 evaluator |

### Paper Trading Gates
| Gate | Metric | Threshold | Source |
|------|--------|-----------|--------|
| 8 | Paper Duration | ≥ 30 days | `state.db` equity_snapshots |
| 9 | Paper PnL | > $0 (any profit) | `state.db` equity_snapshots |
| 10 | No Catastrophe | Max single loss < 10% equity | `state.db` positions |

## Running the Scorecard

```bash
# Check all passports
uv run python -c "
from bot.deploy.go_to_market import GoToMarketScorecard
sc = GoToMarketScorecard()
# See go_to_market.py for evaluate_from_db() usage
"

# Check specific passport
uv run python -c "
from bot.deploy.go_to_market import GoToMarketScorecard
sc = GoToMarketScorecard()
result = sc.evaluate_from_db('PressureReader')
print(result.format_table())
"
```

## Kill Switch

- **Threshold:** 30% drawdown from initial equity ($100 → kill at $70)
- **Action:** Passport disabled, Telegram alert sent
- **Recovery:** Manual re-enable only after review
- **Override:** Per-passport via `config_overrides.KILL_SWITCH_THRESHOLD`

## Deployment Checklist

```
□ Passport passes all 10 gates
□ Kill switch threshold confirmed
□ Production state DB initialized (state_prod.db)
□ Binance API keys configured for REAL trading
□ Telegram alerts verified (test notification sent)
□ Daily report cron job enabled
□ Manual confirmation before first real trade
□ Initial equity deposited ($100 per passport)
```

## Current Candidates

| Passport | Gates Passed | Status | Notes |
|----------|-------------|--------|-------|
| (to be populated after exploration completes) | | | |

## History

- **2026-04-14:** Framework created (Session 13)
```

- [ ] **Step 2: Commit**

```bash
git add docs/GO_TO_MARKET.md
git commit -m "docs: add go-to-market deployment guide with 10-gate framework

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: Update FINDINGS.md with Session 13

**Files:**
- Modify: `docs/FINDINGS.md`

- [ ] **Step 1: Append Session 13 section to FINDINGS.md**

Add to the end of `docs/FINDINGS.md`:

```markdown
---

## §23 Session 13 — Exhaustive Exploration & Go-to-Market Framework (2026-04-14)

### What We Built

1. **Family Verdict Tracker** (`bot/research/verdict_tracker.py`) — SQLite-backed tracker for exploration progress per strategy family. Classifies families into Tier A (strong), Tier B (promising), Tier C (dead) based on Stage 2 survivor counts.

2. **Exhaustive Exploration Runner** (`scripts/exhaust_exploration.py`) — Tier-based research orchestrator:
   - Tier C: Last-chance round (10 combos/family) → retire if still 0 S2
   - Tier B: Sample 20 additional combos
   - Tier A: Complete full parameter grid + Stage 3+4

3. **Go-to-Market Scorecard** (`bot/deploy/go_to_market.py`) — 10-gate automated checker:
   - Gates 1-7: Backtest (return >15%, PF >1.3, MaxDD <40%, 50+ trades, WR >35%, MC robust, orthogonal)
   - Gates 8-10: Paper trading (30d minimum, positive PnL, no catastrophe)

4. **Circuit Breaker** (`bot/risk/circuit_breaker.py`) — Kill switch at 30% drawdown, integrated into PassportRunner scan cycle. Disables passport, sends Telegram alert.

5. **Daily Telegram Report** (`bot/reporting/daily_report.py`) — Automated daily summary of all passport PnL, trade stats, and alerts.

### Family Classification (from research DB)

| Tier | Families | S2 Survivors | Status |
|------|---------|-------------|--------|
| A (Strong) | rsi_momentum(15), hidden_gem_variant(10), rsi_bb_reversal(8), pressure_flow_short(8), bollinger_breakout(7) | 48 | Deep exploration |
| B (Promising) | vwap_deviation(5), pivot_bounce(5), keltner_breakout(5), williams_reversal(3), supertrend_follow(3), stochastic_reversal(3), sniper_variant(3), obv_trend(3), donchian_breakout(3), balanced_all(2) | 35 | Sample + evaluate |
| C (Dead) | 13 families (mfi_flow, pressure_reader, ema_crossover, etc.) | 0 | Last-chance → retire |

### Decisions

- Real money: $100/passport, max 3 passports, no auto-scale
- Kill switch: 30% drawdown = auto-disable
- Paper minimum: 30 days + all 10 gates
- Retirement: ≥40 tested + 0 S2 survivors (after last-chance) = RETIRED
```

- [ ] **Step 2: Commit**

```bash
git add docs/FINDINGS.md
git commit -m "docs: add §23 Session 13 exhaustive exploration + go-to-market to FINDINGS

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: Run Full Test Suite & Final Verification

- [ ] **Step 1: Run complete test suite**

Run: `uv run pytest tests/ -v --tb=short -q`
Expected: All tests pass (889 existing + ~40 new = ~929)

- [ ] **Step 2: Verify exploration runner dry-run works**

Run: `uv run python scripts/exhaust_exploration.py --summary`
Expected: Prints family verdict table with correct tier classifications

- [ ] **Step 3: Verify go-to-market scorecard works**

Run: `uv run python -c "
from bot.deploy.go_to_market import GoToMarketScorecard, ScorecardResult
sc = GoToMarketScorecard()
metrics = {
    'return_pct_180d': 25.0, 'profit_factor': 1.5, 'max_drawdown': 30.0,
    'total_trades': 120, 'win_rate': 42.0, 'mc_profitable_pct': 75.0,
    'correlation_group_rank': 1, 'paper_days': 35, 'paper_pnl': 50.0,
    'max_single_loss_pct': 5.0,
}
result = sc.evaluate('TestPassport', metrics)
print(result.format_table())
assert result.all_passed, 'Expected all gates to pass'
print('✅ Scorecard works')
"`
Expected: All 10 gates pass, scorecard table printed

- [ ] **Step 4: Final commit with all changes**

```bash
git add -A
git status
# Verify no unwanted files
git --no-pager log --oneline -10
```

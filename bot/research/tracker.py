"""Experiment tracker — SQLite-based persistence for research runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from bot.research.types import PassportCandidate, EvalResult, ExperimentResult


class ExperimentTracker:
    """Track research pipeline experiments in SQLite."""

    def __init__(self, db_path: str = "research_experiments.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                run_id TEXT PRIMARY KEY,
                total_generated INTEGER DEFAULT 0,
                stage1_survivors INTEGER DEFAULT 0,
                stage2_survivors INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS passports (
                run_id TEXT,
                passport_id TEXT,
                slug TEXT,
                family TEXT,
                config_overrides TEXT,
                status TEXT DEFAULT 'generated',
                PRIMARY KEY (run_id, passport_id)
            );
            CREATE TABLE IF NOT EXISTS eval_results (
                run_id TEXT,
                passport_id TEXT,
                stage INTEGER,
                passed INTEGER,
                metrics TEXT,
                reject_reason TEXT,
                secondary_reasons TEXT,
                evaluated_at TEXT,
                PRIMARY KEY (run_id, passport_id, stage)
            );
        """)
        self.conn.commit()

    def start_experiment(self, total_generated: int = 0) -> str:
        """Start a new experiment run. Returns run_id."""
        now = datetime.now(timezone.utc)
        run_id = f"exp-{now.strftime('%Y-%m-%d-%H%M%S')}"
        self.conn.execute(
            "INSERT INTO experiments (run_id, total_generated, started_at) VALUES (?, ?, ?)",
            (run_id, total_generated, now.isoformat()),
        )
        self.conn.commit()
        return run_id

    def log_passport(self, run_id: str, passport: PassportCandidate):
        """Log a generated passport candidate."""
        self.conn.execute(
            "INSERT OR REPLACE INTO passports (run_id, passport_id, slug, family, config_overrides, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, passport.passport_id, passport.slug, passport.family,
             json.dumps(passport.config_overrides), passport.status),
        )
        self.conn.commit()

    def log_eval(self, run_id: str, result: EvalResult):
        """Log an evaluation result."""
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "INSERT OR REPLACE INTO eval_results "
            "(run_id, passport_id, stage, passed, metrics, reject_reason, secondary_reasons, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, result.passport_id, result.stage, int(result.passed),
             json.dumps(result.metrics), result.reject_reason,
             json.dumps(result.secondary_reasons), now.isoformat()),
        )
        self.conn.commit()

    def get_passports(self, run_id: str) -> list[dict]:
        """Get all passports for a run."""
        rows = self.conn.execute(
            "SELECT * FROM passports WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_evals(self, run_id: str, stage: Optional[int] = None) -> list[dict]:
        """Get evaluation results, optionally filtered by stage."""
        if stage is not None:
            rows = self.conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ? AND stage = ?",
                (run_id, stage),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ?", (run_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["passed"] = bool(d["passed"])
            result.append(d)
        return result

    def get_survivors(self, run_id: str, stage: int) -> list[str]:
        """Get passport IDs that passed a given stage."""
        rows = self.conn.execute(
            "SELECT passport_id FROM eval_results WHERE run_id = ? AND stage = ? AND passed = 1",
            (run_id, stage),
        ).fetchall()
        return [r["passport_id"] for r in rows]

    def finish_experiment(
        self, run_id: str,
        stage1_survivors: int = 0,
        stage2_survivors: int = 0,
    ) -> ExperimentResult:
        """Mark experiment as finished and return summary."""
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "UPDATE experiments SET stage1_survivors = ?, stage2_survivors = ?, "
            "status = 'completed', finished_at = ? WHERE run_id = ?",
            (stage1_survivors, stage2_survivors, now.isoformat(), run_id),
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM experiments WHERE run_id = ?", (run_id,)
        ).fetchone()

        return ExperimentResult(
            run_id=run_id,
            total_generated=row["total_generated"],
            stage1_survivors=stage1_survivors,
            stage2_survivors=stage2_survivors,
        )

    def close(self):
        """Close database connection."""
        self.conn.close()

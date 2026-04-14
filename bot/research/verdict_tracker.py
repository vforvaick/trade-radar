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

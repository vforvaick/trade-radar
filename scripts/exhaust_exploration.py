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
                    mc_iterations=50,
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

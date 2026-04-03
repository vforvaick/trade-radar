import os
import json
import argparse
from datetime import datetime

from bot.data_fetcher import get_all_futures_symbols
from bot.discovery_engine import StrategyDiscoveryEngine
from bot.walk_forward import walk_forward_validate
from bot.notifier import TelegramNotifier

def run_pipeline(symbols: list[str], interval: str, args):
    print("=" * 60)
    print("🔬 PUMPRADAR STRATEGY DISCOVERY ENGINE")
    print("=" * 60)
    
    engine = StrategyDiscoveryEngine(symbols, interval, days=180)
    
    if args.combos:
        # For testing, truncate combinations
        engine.generate_search_space = lambda: StrategyDiscoveryEngine.generate_search_space(engine)[:args.combos]
    
    top_results = engine.run_discovery(max_workers=args.workers)
    
    print("\n" + "=" * 60)
    print("🚀 WALK-FORWARD VALIDATION (Top 20)")
    print("=" * 60)
    
    top_n = top_results[:args.top_n]
    validated = []
    
    for i, res in enumerate(top_n):
        cfg = res["config"]
        print(f"\n[Validating {i+1}/{len(top_n)}] Vol={cfg['VOLUME_SPIKE_THRESHOLD']} {cfg['_profile_name']} {cfg['_exit_name']}")
        
        wf_res = walk_forward_validate(
            cfg, symbols, interval, 
            train_days=args.train_days, 
            test_days=args.test_days
        )
        
        verdict = wf_res["verdict"]
        print(f"  → Result: {verdict} (Overfit: {wf_res['overfit_score']:.2f}, Test PnL: {wf_res['test_result'].get('return_pct', 0.0):+.1f}%)")
        
        if verdict == "KEEP":
            wf_res["config"] = cfg
            validated.append(wf_res)

    print("\n" + "=" * 60)
    print(f"📁 AUTO-GENERATING PASSPORTS ({len(validated)} KEEPs)")
    print("=" * 60)
    
    out_dir = os.path.join(os.path.dirname(__file__), "pumpradar-passports", "configs", "discovered")
    os.makedirs(out_dir, exist_ok=True)
    
    report_lines = ["🔬 **Discovery Engine Results**\n"]
    
    for i, res in enumerate(validated):
        cfg = res["config"]
        prof = cfg["_profile_name"]
        ex = cfg["_exit_name"]
        vol = cfg["VOLUME_SPIKE_THRESHOLD"]
        
        name = f"Discovery #{i+1} — Vol{vol} {prof} {ex}"
        train_ret = res["train_result"].get("return_pct", 0.0)
        test_ret = res["test_result"].get("return_pct", 0.0)
        sharpe = res["train_result"].get("sharpe", 0.0)
        
        desc = (
            f"Auto-discovered: Vol {vol}, {prof} weights, {ex}. "
            f"Sharpe {sharpe:.2f}, WF-validated."
        )
        
        p = {
            "name": name,
            "emoji": "🔬",
            "description": desc,
            "config_overrides": cfg,
            "metadata": {
                "discovered_at": datetime.now().strftime("%Y-%m-%d"),
                "train_return": f"{train_ret:+.1f}%",
                "test_return": f"{test_ret:+.1f}%",
                "overfit_score": round(res["overfit_score"], 2)
            }
        }
        
        fname = f"discovered_{i+1}_vol{vol}_{prof.lower().replace('-', '_')}_{ex.lower()}.json"
        fpath = os.path.join(out_dir, fname)
        
        with open(fpath, "w") as f:
            json.dump(p, f, indent=4)
            
        print(f"  Created: {fname}")
        report_lines.append(f"✅ **{name}**")
        report_lines.append(f"   Train: {p['metadata']['train_return']} | Test: {p['metadata']['test_return']} | Overfit: {p['metadata']['overfit_score']}")
    
    if args.tg_token and args.tg_chat:
        notifier = TelegramNotifier(bot_token=args.tg_token, chat_id=args.tg_chat)
        if validated:
            notifier._send("\n".join(report_lines))
        else:
            notifier._send("🔬 **Discovery Engine finished**\nNo configurations passed Walk-Forward Validation today.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--pairs", type=int, default=15)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--combos", type=int, default=0, help="Limit combos for testing")
    parser.add_argument("--top-n", type=int, default=20, help="How many top results to WF validate")
    parser.add_argument("--train-days", type=int, default=120)
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument("--tg-token", default=None)
    parser.add_argument("--tg-chat", default=None)
    
    args = parser.parse_args()
    syms = get_all_futures_symbols()[:args.pairs]
    print(f"Loaded {len(syms)} pairs.")
    run_pipeline(syms, args.interval, args)

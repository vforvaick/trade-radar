import os
import json
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from bot import config
from bot.backtester import run_backtest

class StrategyDiscoveryEngine:
    def __init__(self, symbols, interval, days=180):
        self.symbols = symbols
        self.interval = interval
        self.days = days
        self.results_file = "discovery_results.json"

    def generate_search_space(self) -> list[dict]:
        """Generate all parameter combinations."""
        # Define search space
        vol_thresholds = [1.5, 2.0, 2.5, 3.0]
        conf_thresholds = [50, 54, 60, 65, 70]
        exit_strategies = [
            {"USE_ATR_EXITS": False, "USE_TRAILING_STOP": False},
            {"USE_ATR_EXITS": True, "USE_TRAILING_STOP": False},
            {"USE_ATR_EXITS": False, "USE_TRAILING_STOP": True},
            {"USE_ATR_EXITS": True, "USE_TRAILING_STOP": True},
        ]
        
        # Weight Profiles
        weight_profiles = [
            # 1. Equal
            {"volume_spike": 1.0, "pressure": 1.0, "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0, "bb_position": 1.0, "rsi_divergence": 1.0, "candle_direction": 1.0},
            # 2. Volume-Heavy
            {"volume_spike": 3.0, "pressure": 2.0, "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0, "bb_position": 1.0, "rsi_divergence": 1.0, "candle_direction": 1.0},
            # 3. Trend-Purist
            {"volume_spike": 0.5, "pressure": 0.5, "ema_trend": 2.0, "macd_signal": 2.0, "rsi_position": 0.5, "bb_position": 0.5, "rsi_divergence": 0.5, "candle_direction": 1.5},
            # 4. Reversal
            {"volume_spike": 0.0, "pressure": 0.0, "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 2.0, "bb_position": 2.0, "rsi_divergence": 2.0, "candle_direction": 0.0},
            # 5. Minimal (Volume + EMA + BB)
            {"volume_spike": 1.0, "pressure": 0.0, "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0, "bb_position": 1.0, "rsi_divergence": 0.0, "candle_direction": 0.0},
        ]
        
        profile_names = ["Equal", "Volume-Heavy", "Trend-Purist", "Reversal", "Minimal"]
        exit_names = ["Fixed%", "ATR", "Trailing", "ATR+Trailing"]

        combinations = []
        for v in vol_thresholds:
            for c in conf_thresholds:
                for w_idx, w in enumerate(weight_profiles):
                    for ex_idx, ex in enumerate(exit_strategies):
                        cfg = {
                            "VOLUME_SPIKE_THRESHOLD": v,
                            "CONFIDENCE_THRESHOLD": c,
                            "INDICATOR_WEIGHTS": w,
                            "_profile_name": profile_names[w_idx],
                            "_exit_name": exit_names[ex_idx]
                        }
                        cfg.update(ex)
                        combinations.append(cfg)
        
        return combinations

    def _backtest_config(self, config_override: dict) -> dict:
        """Single backtest run with config. Returns summary + config."""
        summary = run_backtest(self.symbols, self.interval, self.days, cfg_override=config_override)
        
        # Don't store the massive trade_details in discovery results to save memory/disk
        if "trade_details" in summary:
            del summary["trade_details"]
            
        return {
            "config": config_override,
            "summary": summary
        }

    def run_discovery(self, max_workers=1) -> list[dict]:
        """Run full grid search. Returns sorted results."""
        combinations = self.generate_search_space()
        total = len(combinations)
        print(f"[Discovery] Generated {total} combinations in search space.")
        
        completed = []
        # Load existing progress if available
        if os.path.exists(self.results_file):
            try:
                with open(self.results_file, 'r') as f:
                    completed = json.load(f)
                print(f"[Discovery] Resuming from {len(completed)} existing results.")
            except Exception as e:
                print(f"[Discovery] Failed to load existing results: {e}")
                
        # Filter combinations to those not yet completed
        completed_configs = [json.dumps(r["config"], sort_keys=True) for r in completed]
        pending = [c for c in combinations if json.dumps(c, sort_keys=True) not in completed_configs]
        
        print(f"[Discovery] Pending tasks: {len(pending)}")
        
        results = list(completed)
        best_return = max([r["summary"]["return_pct"] for r in results]) if results else -999.0
        
        if max_workers == 1:
            for i, cfg in enumerate(pending):
                res = self._backtest_config(cfg)
                results.append(res)
                
                # Update Best
                ret = res["summary"]["return_pct"]
                if ret > best_return:
                    best_return = ret
                
                # Progress Reporting
                progress_pct = (len(results) / total) * 100
                vol = cfg["VOLUME_SPIKE_THRESHOLD"]
                prof = cfg["_profile_name"]
                ex_name = cfg["_exit_name"]
                print(f"[Discovery] {len(results)}/{total} ({progress_pct:.1f}%) — Best so far: {best_return:+.1f}% (Vol{vol}, {prof}, {ex_name})", flush=True)
                
                # Save Progress
                with open(self.results_file, 'w') as f:
                    json.dump(results, f, indent=2)
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._backtest_config, cfg): cfg for cfg in pending}
                for future in as_completed(futures):
                    res = future.result()
                    results.append(res)
                    cfg = res["config"]
                    
                    # Update Best
                    ret = res["summary"]["return_pct"]
                    if ret > best_return:
                        best_return = ret
                    
                    # Progress Reporting
                    progress_pct = (len(results) / total) * 100
                    vol = cfg["VOLUME_SPIKE_THRESHOLD"]
                    prof = cfg["_profile_name"]
                    ex_name = cfg["_exit_name"]
                    print(f"[Discovery] {len(results)}/{total} ({progress_pct:.1f}%) — Best so far: {best_return:+.1f}% (Vol{vol}, {prof}, {ex_name})", flush=True)
                    
                    # Save Progress
                    with open(self.results_file, 'w') as f:
                        json.dump(results, f, indent=2)
                        
        # Sort by Sharpe Ratio (descending)
        results.sort(key=lambda x: x["summary"].get("sharpe", 0.0) or 0.0, reverse=True)
        return results[:20] # Return top 20

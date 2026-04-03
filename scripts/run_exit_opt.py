import os
import sys

# Ensure project root is in path when the script is executed directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bot.backtester import run_backtest
from bot.data_fetcher import get_all_futures_symbols

def run():
    print("="*60)
    print("PHASE 1: EXIT MANAGEMENT OPTIMIZATION (180 DAYS)")
    print("="*60)
    
    symbols = get_all_futures_symbols()[:15]  # Top 15 pairs
    days = 180
    
    # We lock the base strategy parameters to the Rank #2 Baseline
    base_params = {
        "EMA_FAST": 9, 
        "EMA_MID": 21, 
        "EMA_SLOW": 50, 
        "VOLUME_SPIKE_THRESHOLD": 2.0
    }
    
    combos = [
        # Option 1: Base (Fixed % Exits, No Trailing Stop)
        {'USE_ATR_EXITS': False, 'USE_TRAILING_STOP': False},
        # Option 2: ATR Exits (Dynamic TP/SL, No Trailing Stop)
        {'USE_ATR_EXITS': True, 'USE_TRAILING_STOP': False},
        # Option 3: Trailing Stops (Fixed % Exits + Trailing after TP1)
        {'USE_ATR_EXITS': False, 'USE_TRAILING_STOP': True},
        # Option 4: Full Dynamic (ATR Exits + Trailing after TP1)
        {'USE_ATR_EXITS': True, 'USE_TRAILING_STOP': True}
    ]

    results = []
    
    for i, combo in enumerate(combos):
        # Merge base params into combo
        full_config = {**base_params, **combo}
        print(f"\n[Grid {i+1}/4] Testing Exits: {combo}")
        
        # Run backtest
        summary = run_backtest(symbols, "1h", days, cfg_override=full_config)
        summary["params"] = combo
        results.append(summary)
        
        print(f"  Result: {summary['trades']} trades | WR: {summary['win_rate']:.1f}% | Return: {summary['return_pct']:+.1f}% | MaxDD: {summary.get('max_dd', 0):.1f}%")

    print("\n" + "="*60)
    print("EXIT OPTIMIZATION RESULTS (Sorted by Return)")
    print("="*60)
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    for i, r in enumerate(results):
         print(f"#{i+1}: Return={r['return_pct']:+.1f}% WR={r['win_rate']:.1f}% Trades={r['trades']} Params={r['params']}")

if __name__ == "__main__":
    run()

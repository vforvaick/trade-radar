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
    print("PHASE 3: TWIN BOTS (MOMENTUM VS REVERSAL)")
    print("="*60)
    
    symbols = get_all_futures_symbols()[:10]
    days = 180
    
    # Base configuration
    base_params = {
        "EMA_FAST": 9, 
        "EMA_MID": 21, 
        "EMA_SLOW": 50, 
        "VOLUME_SPIKE_THRESHOLD": 2.0
    }
    
    # Keys MUST match config.INDICATOR_WEIGHTS canonical keys
    combos = [
        # Option 1: Standard Momentum
        {
            'INDICATOR_WEIGHTS': {
                'REVERSAL_MODE': False,
                'ema_trend': 1.0,
                'macd_signal': 1.0,
                'rsi_position': 1.0,
                'rsi_divergence': 1.0,
                'bb_position': 1.0,
                'volume_spike': 2.0,
                'pressure': 1.0,
                'candle_direction': 1.0,
            }
        },
        # Option 2: Pure Mean Reversion
        {
            'INDICATOR_WEIGHTS': {
                'REVERSAL_MODE': True,
                'ema_trend': 0.0,          # Ignore EMA trend
                'macd_signal': 0.0,         # Ignore MACD trend
                'rsi_position': 2.0,        # Heavily weight oversold/overbought RSI
                'rsi_divergence': 1.0,
                'bb_position': 2.0,         # Heavily weight BB extreme touches
                'volume_spike': 2.0,        # Still need volume confirmation
                'pressure': 0.0,            # Ignore short term pressure
                'candle_direction': 0.0,    # Ignore candle direction
            }
        }
    ]

    results = []
    
    for i, combo in enumerate(combos):
        full_config = {**base_params, **combo}
        is_rev = combo['INDICATOR_WEIGHTS']['REVERSAL_MODE']
        print(f"\n[Test {i+1}/2] Mode: {'REVERSAL' if is_rev else 'MOMENTUM'}")
        
        # Run backtest
        summary = run_backtest(symbols, "1h", days, cfg_override=full_config)
        summary["params"] = combo
        results.append(summary)
        
        print(f"  Result: {summary['trades']} trades | WR: {summary['win_rate']:.1f}% | Return: {summary['return_pct']:+.1f}% | MaxDD: {summary.get('max_dd', 0):.1f}%")

    print("\n" + "="*60)
    print("TWIN BOTS RESULTS (Sorted by Return)")
    print("="*60)
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    for i, r in enumerate(results):
         mode = 'REVERSAL' if r['params']['INDICATOR_WEIGHTS']['REVERSAL_MODE'] else 'MOMENTUM'
         print(f"#{i+1}: {mode} | Return={r['return_pct']:+.1f}% WR={r['win_rate']:.1f}% Trades={r['trades']}")

if __name__ == "__main__":
    run()

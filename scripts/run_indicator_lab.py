import os
import sys
import random

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from bot.backtester import run_backtest
from bot.data_fetcher import get_all_futures_symbols

def run():
    print("="*60)
    print("PHASE 2: INDICATOR LABORATORY (RANDOM WEIGHT SEARCH)")
    print("="*60)
    
    symbols = get_all_futures_symbols()[:10]
    days = 180
    
    # We lock the base strategy parameters
    base_params = {
        "EMA_FAST": 9, 
        "EMA_MID": 21, 
        "EMA_SLOW": 50, 
        "VOLUME_SPIKE_THRESHOLD": 2.0
    }
    
    results = []
    
    # Generate 10 random indicator weight configurations
    # Keys MUST match config.INDICATOR_WEIGHTS canonical keys
    for i in range(10):
        weights = {
            'ema_trend': random.choice([1.0, 2.0]),        # Core trend
            'macd_signal': random.choice([0.0, 1.0]),       # Toggle MACD
            'rsi_position': random.choice([0.0, 1.0]),      # Toggle RSI
            'rsi_divergence': random.choice([0.0, 1.0]),    # Toggle divergence
            'bb_position': random.choice([0.0, 1.0]),       # Toggle Bollinger
            'volume_spike': random.choice([1.0, 1.5, 2.0]), # Volume confirmation 
            'pressure': random.choice([0.0, 0.5, 1.0]),     # Pressure signal
            'candle_direction': random.choice([0.0, 1.0]),   # Toggle candle dir
        }
        
        full_config = {**base_params, 'INDICATOR_WEIGHTS': weights}
        
        print(f"\n[Lab Run {i+1}/10] Weights: {weights}")
        
        summary = run_backtest(symbols, "1h", days, cfg_override=full_config)
        summary["weights"] = weights
        results.append(summary)
        
        print(f"  Result: {summary['trades']} trades | WR: {summary['win_rate']:.1f}% | Return: {summary['return_pct']:+.1f}% | MaxDD: {summary.get('max_dd', 0):.1f}%")

    print("\n" + "="*60)
    print("INDICATOR LAB RESULTS (Sorted by Return)")
    print("="*60)
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    for i, r in enumerate(results):
         print(f"#{i+1}: Return={r['return_pct']:+.1f}% WR={r['win_rate']:.1f}% Trades={r['trades']}")
         print(f"      Weights: {r['weights']}")

if __name__ == "__main__":
    run()

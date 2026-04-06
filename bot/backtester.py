"""
Backtester — runs the full pipeline on historical data.
Supports: validation mode, basic backtest, and parameter grid search.
"""
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from bot import config
from bot.data_fetcher import fetch_klines_range, fetch_klines, get_all_futures_symbols
from bot.indicators import calc_ema
from bot.scorer import score_confluence
from bot.signals import generate_signal
from bot.position_manager import PositionManager


def determine_btc_trend_at(btc_df: pd.DataFrame, timestamp: pd.Timestamp) -> str:
    """Determine BTC trend at a specific point in time."""
    mask = btc_df["timestamp"] <= timestamp
    subset = btc_df[mask].tail(30)
    if len(subset) < 25:
        return "Sideways"

    ema9 = calc_ema(subset["close"], 9)
    ema21 = calc_ema(subset["close"], 21)
    diff_pct = (ema9.iloc[-1] - ema21.iloc[-1]) / ema21.iloc[-1] * 100

    if diff_pct > 0.5:
        return "Uptrend"
    elif diff_pct < -0.5:
        return "Downtrend"
    return "Sideways"


def backtest_pair(symbol: str, klines: pd.DataFrame, btc_df: pd.DataFrame,
                  cfg_override: dict = None) -> list[dict]:
    """
    Run backtest on a single pair.

    Walk through klines candle by candle:
    1. At each candle close, score confluence
    2. If GO → generate signal → open position
    3. Check open positions against candle high/low

    Returns list of trade results.
    """
    # Apply config overrides for grid search
    original = {}
    if cfg_override:
        for k, v in cfg_override.items():
            original[k] = getattr(config, k, None)
            setattr(config, k, v)

    pm = PositionManager()
    equity = config.INITIAL_EQUITY
    trades = []
    lookback = 60  # candles needed for indicators

    for i in range(lookback, len(klines)):
        window = klines.iloc[i - lookback:i + 1].copy().reset_index(drop=True)
        ts = klines.iloc[i]["timestamp"]
        high = klines.iloc[i]["high"]
        low = klines.iloc[i]["low"]
        close = klines.iloc[i]["close"]

        # Update existing positions with this candle
        prices = {symbol: (high, low, close)}
        events = pm.update_positions(prices)

        for pos, event in events:
            if event in ("SL_HIT", "SL_BREAKEVEN", "TP3_HIT"):
                equity += pos.realized_pnl
                trades.append({
                    "symbol": symbol,
                    "direction": pos.signal.direction,
                    "entry": pos.signal.entry_price,
                    "exit_event": pos.status,
                    "pnl": pos.realized_pnl,
                    "equity_after": equity,
                    "confidence": pos.signal.confidence,
                    "leverage": pos.signal.leverage,
                    "entry_time": pos.signal.timestamp,
                    "exit_time": ts,
                    "tp1_hit": pos.tp1_hit,
                    "tp2_hit": pos.tp2_hit,
                    "tp3_hit": pos.tp3_hit,
                })

        # Score confluence at candle close
        if pm.can_open():
            btc_trend = determine_btc_trend_at(btc_df, ts)
            result = score_confluence(window, btc_trend)

            if result["go"]:
                signal = generate_signal(symbol, close, result, timestamp=ts)
                if signal:
                    pm.open_position(signal, equity)

    # Close any remaining positions at market
    for pos in pm.positions:
        last_close = klines.iloc[-1]["close"]
        entry = pos.signal.entry_price
        is_long = pos.signal.direction == "LONG"
        leverage = pos.signal.leverage
        sl_dist = abs(pos.signal.sl - entry) / entry

        # Determine remaining open fraction (don't double-count already-closed TP portions)
        if pos.tp2_hit:
            remaining_fraction = config.TP3_CLOSE_PCT
        elif pos.tp1_hit:
            remaining_fraction = config.TP2_CLOSE_PCT + config.TP3_CLOSE_PCT
        else:
            remaining_fraction = 1.0

        pnl_pct = (last_close - entry) / entry if is_long else (entry - last_close) / entry
        pnl_on_remaining = pos.risk_amount * (pnl_pct / sl_dist) * leverage * remaining_fraction
        fee = pos.risk_amount * leverage * remaining_fraction * (config.TRADING_FEE_PCT / 100) * 2
        pos.realized_pnl += pnl_on_remaining - fee

        equity += pos.realized_pnl
        trades.append({
            "symbol": symbol,
            "direction": pos.signal.direction,
            "entry": pos.signal.entry_price,
            "exit_event": "MARKET_CLOSE",
            "pnl": pos.realized_pnl,
            "equity_after": equity,
            "entry_time": pos.signal.timestamp,
            "exit_time": klines.iloc[-1]["timestamp"],
            "tp1_hit": pos.tp1_hit,
            "tp2_hit": pos.tp2_hit,
            "tp3_hit": pos.tp3_hit,
        })

    # Restore config
    for k, v in original.items():
        setattr(config, k, v)

    return trades


def run_backtest(symbols: list[str], interval: str = "1h",
                 days: int = 90, cfg_override: dict = None,
                 end_offset_days: int = 0) -> dict:
    """
    Run backtest across multiple pairs.

    Aggregates per-symbol summaries (equal-weight portfolio interpretation) so
    that return_pct and max_dd are meaningful — each symbol contributes one
    independent equity curve starting at INITIAL_EQUITY.

    Returns summary stats + per-trade details.
    """
    end_ms = int(time.time() * 1000) - (end_offset_days * 24 * 3600 * 1000)
    start_ms = end_ms - (days * 24 * 3600 * 1000)

    print(f"[Backtest] Fetching BTC data...", flush=True)
    btc_df = fetch_klines_range("BTCUSDT", interval, start_ms, end_ms)

    all_trades = []
    sym_summaries = []
    for i, sym in enumerate(symbols):
        print(f"[Backtest] ({i+1}/{len(symbols)}) {sym}...", flush=True)
        try:
            klines = fetch_klines_range(sym, interval, start_ms, end_ms)
            if len(klines) < 100:
                print(f"  Skipping {sym}: only {len(klines)} candles", flush=True)
                continue
            trades = backtest_pair(sym, klines, btc_df, cfg_override)
            all_trades.extend(trades)
            sym_summaries.append(_summarize(trades))
            print(f"  → {len(trades)} trades", flush=True)
        except Exception as e:
            print(f"  Error {sym}: {e}", flush=True)
            continue

    if not sym_summaries:
        return _summarize([])

    # Build aggregate from per-symbol summaries (equal-weight portfolio)
    combined = _summarize(all_trades)
    active = [s for s in sym_summaries if s["trades"] > 0]
    if active:
        combined["return_pct"] = sum(s["return_pct"] for s in active) / len(active)
        combined["max_dd"] = sum(s["max_dd"] for s in active) / len(active)
    return combined


def run_grid_search(symbols: list[str], interval: str, days: int = 90):
    """
    Grid search over key parameters to find optimal combination.
    Tests: EMA periods, volume threshold, confidence threshold.
    """
    param_grid = [
        {"EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50, "VOLUME_SPIKE_THRESHOLD": 1.5},
        {"EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 55, "VOLUME_SPIKE_THRESHOLD": 1.5},
        {"EMA_FAST": 8, "EMA_MID": 21, "EMA_SLOW": 55, "VOLUME_SPIKE_THRESHOLD": 2.0},
        {"EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50, "VOLUME_SPIKE_THRESHOLD": 2.0},
        {"EMA_FAST": 5, "EMA_MID": 13, "EMA_SLOW": 34, "VOLUME_SPIKE_THRESHOLD": 1.5},
    ]

    results = []
    for i, params in enumerate(param_grid):
        print(f"\n{'='*60}", flush=True)
        print(f"[Grid {i+1}/{len(param_grid)}] {params}", flush=True)
        print(f"{'='*60}", flush=True)

        summary = run_backtest(symbols, interval, days, cfg_override=params)
        summary["params"] = params
        results.append(summary)

        print(f"  Result: {summary['trades']} trades, "
              f"WR: {summary['win_rate']:.1f}%, "
              f"Return: {summary['return_pct']:+.1f}%", flush=True)

    # Sort by return
    results.sort(key=lambda x: x["return_pct"], reverse=True)

    print(f"\n{'='*60}", flush=True)
    print(f"GRID SEARCH RESULTS (sorted by return)", flush=True)
    print(f"{'='*60}", flush=True)
    for i, r in enumerate(results):
        print(f"#{i+1}: Return={r['return_pct']:+.1f}% WR={r['win_rate']:.1f}% "
              f"Trades={r['trades']} Params={r['params']}", flush=True)

    return results


def _summarize(trades: list[dict]) -> dict:
    """Summarize backtest results."""
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "return_pct": 0.0, "max_dd": 0.0, "final_equity": config.INITIAL_EQUITY, "profit_factor": 0.0}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]

    # Calculate max drawdown from equity curve
    equities = [config.INITIAL_EQUITY] + [t["equity_after"] for t in trades]
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100
        max_dd = max(max_dd, dd)

    # Calculate Ratios
    sharpe = 0.0
    sortino = 0.0
    calmar = 0.0
    final_eq = equities[-1]
    
    if trades:
        try:
            times = pd.to_datetime([t["exit_time"] for t in trades])
            eq_series = pd.Series(equities[1:], index=times)
            start_time = times.min() - pd.Timedelta(days=1)
            eq_series.loc[start_time] = config.INITIAL_EQUITY
            eq_series = eq_series.sort_index()
            
            daily_equity = eq_series.resample('D').last().ffill()
            daily_returns = daily_equity.pct_change().dropna()
            
            days_passed = max(1, (daily_equity.index.max() - daily_equity.index.min()).days)
            annual_ret = (final_eq / config.INITIAL_EQUITY) ** (365 / days_passed) - 1
            
            std_dev = daily_returns.std()
            if not np.isnan(std_dev) and std_dev != 0:
                sharpe = (daily_returns.mean() / std_dev) * np.sqrt(365)
            
            neg_returns = daily_returns[daily_returns < 0]
            neg_std = neg_returns.std()
            if not np.isnan(neg_std) and neg_std != 0:
                sortino = (daily_returns.mean() / neg_std) * np.sqrt(365)
            elif len(neg_returns) == 0 and len(daily_returns) > 0:
                sortino = 100.0 if daily_returns.mean() > 0 else 0.0
                
            calmar = annual_ret / (max_dd / 100) if max_dd > 0 else 100.0
        except Exception:
            pass

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "total_pnl": sum(t["pnl"] for t in trades),
        "return_pct": (final_eq / config.INITIAL_EQUITY - 1) * 100,
        "final_equity": final_eq,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "avg_win": np.mean([t["pnl"] for t in wins]) if wins else 0,
        "avg_loss": np.mean([t["pnl"] for t in losses]) if losses else 0,
        "profit_factor": (sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses))
                         if losses and sum(t["pnl"] for t in losses) != 0 else float("inf")),
        "trade_details": trades,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pumpradar Strategy Backtester")
    parser.add_argument("--mode", choices=["backtest", "optimize"], default="backtest")
    parser.add_argument("--interval", default="1h", help="Candle timeframe")
    parser.add_argument("--days", type=int, default=30, help="Days of history")
    parser.add_argument("--pairs", type=int, default=10, help="Top N pairs by volume")
    args = parser.parse_args()

    print(f"Fetching top {args.pairs} pairs by volume...", flush=True)
    all_syms = get_all_futures_symbols()
    symbols = all_syms[:args.pairs]
    print(f"Pairs: {symbols}", flush=True)

    if args.mode == "backtest":
        result = run_backtest(symbols, args.interval, args.days)
        print(f"\n{'='*60}", flush=True)
        print(f"BACKTEST RESULTS", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"Trades: {result['trades']}", flush=True)
        print(f"Win Rate: {result['win_rate']:.1f}%", flush=True)
        print(f"Return: {result['return_pct']:+.1f}%", flush=True)
        print(f"Max Drawdown: {result['max_dd']:.1f}%", flush=True)
        print(f"Profit Factor: {result['profit_factor']:.2f}", flush=True)
        print(f"Final Equity: ${result['final_equity']:,.0f}", flush=True)

    elif args.mode == "optimize":
        results = run_grid_search(symbols, args.interval, args.days)

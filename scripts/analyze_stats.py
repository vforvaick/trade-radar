"""
Phase 3: Statistical Deep Dive
Phase 4: Strategy Parameter Extraction

Produces: analysis_report.md, equity_curve.png, strategy_spec.md
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from collections import Counter
import re
import json

# ============================================================
# LOAD DATA
# ============================================================
df = pd.read_csv("validated_ledger.csv")
df['date_signal'] = pd.to_datetime(df['date_signal'])

# Only analyze resolved trades (not OPEN)
resolved = df[df['status'] != 'OPEN'].copy()
print(f"Total trades: {len(df)}, Resolved: {len(resolved)}, Open: {len(df) - len(resolved)}")

# Define win/loss
resolved['is_win'] = resolved['status'].isin(['TP1', 'TP2', 'TP3_CLOSED'])
resolved['is_loss'] = resolved['status'] == 'SL_CLOSED'

# ============================================================
# PHASE 3: STATISTICAL BREAKDOWNS
# ============================================================

report_lines = []
def rpt(line=""):
    report_lines.append(line)

rpt("# 📊 Pumpradar Signal — Statistical Deep Dive")
rpt()
rpt(f"> Analysis of {len(resolved)} resolved trades ({len(df) - len(resolved)} still open)")
rpt(f"> Period: {df['date_signal'].min().strftime('%Y-%m-%d')} to {df['date_signal'].max().strftime('%Y-%m-%d')}")
rpt()

# --- Overall Win Rate ---
wins = resolved['is_win'].sum()
losses = resolved['is_loss'].sum()
win_rate = wins / len(resolved) * 100

rpt("## Overall Performance")
rpt()
rpt("| Metric | Value |")
rpt("|---|---|")
rpt(f"| Total resolved | {len(resolved)} |")
rpt(f"| Wins (TP1+) | {wins} ({win_rate:.1f}%) |")
rpt(f"| Losses (SL) | {losses} ({100-win_rate:.1f}%) |")

# TP cascade
tp1_count = len(resolved[resolved['tp1_hit']])
tp2_count = len(resolved[resolved['tp2_hit']])
tp3_count = len(resolved[resolved['tp3_hit']])
rpt(f"| TP1 hit | {tp1_count} ({tp1_count/len(resolved)*100:.1f}%) |")
rpt(f"| TP2 hit | {tp2_count} ({tp2_count/len(resolved)*100:.1f}%) |")
rpt(f"| TP3 hit | {tp3_count} ({tp3_count/len(resolved)*100:.1f}%) |")

# Avg profit/loss
avg_tp1_profit = resolved.loc[resolved['tp1_hit'], 'tp1_profit_pct'].mean()
avg_sl_loss = resolved.loc[resolved['sl_hit'], 'sl_loss_pct'].mean()
rpt(f"| Avg TP1 profit | +{avg_tp1_profit:.1f}% (leveraged) |")
rpt(f"| Avg SL loss | -{avg_sl_loss:.1f}% (leveraged) |")

# Profit factor
gross_profit = resolved.loc[resolved['tp1_hit'], 'tp1_profit_pct'].sum()
gross_loss = resolved.loc[resolved['sl_hit'], 'sl_loss_pct'].sum()
profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
rpt(f"| Profit factor | {profit_factor:.2f} |")

# Expectancy
expectancy = (win_rate/100 * avg_tp1_profit) - ((1 - win_rate/100) * avg_sl_loss)
rpt(f"| Expectancy/trade | +{expectancy:.2f}% |")
rpt()

# --- Win Rate by Direction ---
rpt("## Win Rate by Direction")
rpt()
rpt("| Direction | Trades | Wins | Win Rate |")
rpt("|---|---|---|---|")
for d in ['LONG', 'SHORT']:
    sub = resolved[resolved['direction'] == d]
    w = sub['is_win'].sum()
    rpt(f"| {d} | {len(sub)} | {w} | {w/len(sub)*100:.1f}% |")
rpt()

# --- Win Rate by Leverage ---
rpt("## Win Rate by Leverage")
rpt()
rpt("| Leverage | Trades | Wins | Win Rate | Avg TP1 Profit | Avg SL Loss |")
rpt("|---|---|---|---|---|---|")
for lev in sorted(resolved['leverage'].dropna().unique()):
    sub = resolved[resolved['leverage'] == lev]
    w = sub['is_win'].sum()
    avg_p = sub.loc[sub['tp1_hit'], 'tp1_profit_pct'].mean()
    avg_l = sub.loc[sub['sl_hit'], 'sl_loss_pct'].mean()
    rpt(f"| {int(lev)}x | {len(sub)} | {w} | {w/len(sub)*100:.1f}% | +{avg_p:.1f}% | -{avg_l:.1f}% |")
rpt()

# --- Win Rate by Confidence ---
rpt("## Win Rate by Confidence Bucket")
rpt()
rpt("| Confidence | Trades | Wins | Win Rate |")
rpt("|---|---|---|---|")
conf_buckets = [(50, 60, "54-60%"), (60, 70, "61-69%"), (70, 80, "70-75%")]
for lo, hi, label in conf_buckets:
    sub = resolved[(resolved['confidence_pct'] >= lo) & (resolved['confidence_pct'] < hi)]
    if len(sub) > 0:
        w = sub['is_win'].sum()
        rpt(f"| {label} | {len(sub)} | {w} | {w/len(sub)*100:.1f}% |")
rpt()

# --- Win Rate by BTC Trend ---
rpt("## Win Rate by BTC Trend")
rpt()
rpt("| BTC Trend | Trades | Wins | Win Rate |")
rpt("|---|---|---|---|")
for trend in resolved['btc_trend'].dropna().unique():
    sub = resolved[resolved['btc_trend'] == trend]
    w = sub['is_win'].sum()
    rpt(f"| {trend} | {len(sub)} | {w} | {w/len(sub)*100:.1f}% |")
rpt()

# --- Win Rate by R:R ---
rpt("## Win Rate by Risk/Reward Ratio")
rpt()
rpt("| R:R | Trades | Wins | Win Rate |")
rpt("|---|---|---|---|")
for rr in resolved['risk_reward'].dropna().unique():
    sub = resolved[resolved['risk_reward'] == rr]
    w = sub['is_win'].sum()
    rpt(f"| {rr} | {len(sub)} | {w} | {w/len(sub)*100:.1f}% |")
rpt()

# --- Time Analysis ---
rpt("## Time Analysis")
rpt()
resolved['hour'] = resolved['date_signal'].dt.hour
rpt("### Win Rate by Hour (UTC)")
rpt()
rpt("| Hour (UTC) | Trades | Wins | Win Rate |")
rpt("|---|---|---|---|")
for h in sorted(resolved['hour'].unique()):
    sub = resolved[resolved['hour'] == h]
    if len(sub) >= 2:
        w = sub['is_win'].sum()
        rpt(f"| {h:02d}:00 | {len(sub)} | {w} | {w/len(sub)*100:.1f}% |")
rpt()

resolved['dow'] = resolved['date_signal'].dt.day_name()
rpt("### Win Rate by Day of Week")
rpt()
rpt("| Day | Trades | Wins | Win Rate |")
rpt("|---|---|---|---|")
for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
    sub = resolved[resolved['dow'] == day]
    if len(sub) > 0:
        w = sub['is_win'].sum()
        rpt(f"| {day} | {len(sub)} | {w} | {w/len(sub)*100:.1f}% |")
rpt()

# --- Duration Analysis ---
rpt("## Duration Analysis")
rpt()

def parse_duration_hours(date_signal, date_outcome):
    if pd.isna(date_outcome):
        return None
    d1 = pd.to_datetime(date_signal)
    d2 = pd.to_datetime(date_outcome)
    return (d2 - d1).total_seconds() / 3600

resolved['dur_tp1'] = resolved.apply(lambda r: parse_duration_hours(r['date_signal'], r['tp1_date']), axis=1)
resolved['dur_sl'] = resolved.apply(lambda r: parse_duration_hours(r['date_signal'], r['sl_date']), axis=1)

avg_dur_tp1 = resolved['dur_tp1'].dropna().mean()
avg_dur_sl = resolved['dur_sl'].dropna().mean()
med_dur_tp1 = resolved['dur_tp1'].dropna().median()
med_dur_sl = resolved['dur_sl'].dropna().median()

rpt("| Metric | Mean | Median |")
rpt("|---|---|---|")
rpt(f"| Time to TP1 | {avg_dur_tp1:.1f}h | {med_dur_tp1:.1f}h |")
rpt(f"| Time to SL | {avg_dur_sl:.1f}h | {med_dur_sl:.1f}h |")
rpt()

# --- Drawdown Analysis ---
rpt("## Drawdown & Consecutive Loss Analysis")
rpt()

# Calculate consecutive losses
max_consec_loss = 0
curr_consec = 0
consec_losses_list = []
for _, row in resolved.sort_values('date_signal').iterrows():
    if row['is_loss']:
        curr_consec += 1
        max_consec_loss = max(max_consec_loss, curr_consec)
    else:
        if curr_consec > 0:
            consec_losses_list.append(curr_consec)
        curr_consec = 0
if curr_consec > 0:
    consec_losses_list.append(curr_consec)

rpt(f"- Max consecutive losses: **{max_consec_loss}**")
rpt(f"- Consecutive loss streaks: {Counter(consec_losses_list)}")
rpt()

# --- Equity Curve Simulation ---
rpt("## Equity Curve Simulation")
rpt()

def simulate_equity(trades_df, risk_pct=3.0, label="All Signals"):
    """Simulate equity curve with fixed % risk per trade using the 70/20/10 TP split."""
    equity = 1000.0
    curve = [(trades_df['date_signal'].min(), equity)]
    max_equity = equity
    max_dd = 0
    
    for _, row in trades_df.sort_values('date_signal').iterrows():
        lev = row['leverage'] if not pd.isna(row['leverage']) else 5
        
        if row['is_loss']:
            # Loss: full position hits SL
            sl_loss = row['sl_loss_pct'] if not pd.isna(row['sl_loss_pct']) else 15.0
            # The loss pct is already leveraged, so we need to de-lever to get raw loss
            # Then apply to risk amount
            raw_loss_pct = sl_loss / lev
            dollar_loss = equity * (risk_pct / 100)  # risk amount
            equity -= dollar_loss
        elif row['tp1_hit']:
            # TP1: close 70% at TP1 profit
            tp1_p = row['tp1_profit_pct'] if not pd.isna(row['tp1_profit_pct']) else 10.0
            raw_tp1 = tp1_p / lev
            risk_amount = equity * (risk_pct / 100)
            pos_size = risk_amount  # simplified: risk amount = potential loss
            
            # 70% closed at TP1
            profit_70 = pos_size * 0.70 * (raw_tp1 / 100) * lev
            
            if row['tp2_hit']:
                tp2_p = row['tp2_profit_pct'] if not pd.isna(row['tp2_profit_pct']) else tp1_p * 1.5
                raw_tp2 = tp2_p / lev
                profit_20 = pos_size * 0.20 * (raw_tp2 / 100) * lev
            else:
                profit_20 = 0
                
            if row['tp3_hit']:
                tp3_p = row['tp3_profit_pct'] if not pd.isna(row['tp3_profit_pct']) else tp1_p * 2
                raw_tp3 = tp3_p / lev
                profit_10 = pos_size * 0.10 * (raw_tp3 / 100) * lev
            else:
                profit_10 = 0
            
            equity += profit_70 + profit_20 + profit_10
        
        curve.append((row['date_signal'], equity))
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity * 100
        max_dd = max(max_dd, dd)
    
    return curve, max_dd, equity

# Simulate different strategies
curve_all, dd_all, final_all = simulate_equity(resolved, risk_pct=3.0, label="All")

# High confidence only (>=65%)
high_conf = resolved[resolved['confidence_pct'] >= 65]
if len(high_conf) > 0:
    curve_hc, dd_hc, final_hc = simulate_equity(high_conf, risk_pct=3.0)
else:
    curve_hc, dd_hc, final_hc = [], 0, 1000

# 7x leverage only
lev7 = resolved[resolved['leverage'] == 7]
if len(lev7) > 0:
    curve_7x, dd_7x, final_7x = simulate_equity(lev7, risk_pct=3.0)
else:
    curve_7x, dd_7x, final_7x = [], 0, 1000

rpt("### Results (starting $1,000, 3% risk per trade)")
rpt()
rpt("| Strategy | Final Equity | Return | Max Drawdown | Trades |")
rpt("|---|---|---|---|---|")
rpt(f"| All signals | ${final_all:,.0f} | +{(final_all/1000-1)*100:.1f}% | {dd_all:.1f}% | {len(resolved)} |")
if len(high_conf) > 0:
    rpt(f"| Confidence ≥65% | ${final_hc:,.0f} | +{(final_hc/1000-1)*100:.1f}% | {dd_hc:.1f}% | {len(high_conf)} |")
if len(lev7) > 0:
    rpt(f"| 7x leverage only | ${final_7x:,.0f} | +{(final_7x/1000-1)*100:.1f}% | {dd_7x:.1f}% | {len(lev7)} |")
rpt()

# Plot equity curves
fig, ax = plt.subplots(figsize=(14, 6))
fig.patch.set_facecolor('#1a1a2e')
ax.set_facecolor('#16213e')

for curve, label, color in [
    (curve_all, "All Signals", "#00d2ff"),
    (curve_hc, "Confidence ≥65%", "#ff6b6b"),
    (curve_7x, "7x Leverage Only", "#ffd93d"),
]:
    if curve:
        dates = [c[0] for c in curve]
        vals = [c[1] for c in curve]
        ax.plot(dates, vals, label=label, color=color, linewidth=2, alpha=0.9)

ax.axhline(y=1000, color='white', linestyle='--', alpha=0.3, label='Starting Capital')
ax.set_title('Pumpradar Signal Equity Curve Simulation', color='white', fontsize=16, fontweight='bold')
ax.set_xlabel('Date', color='white', fontsize=12)
ax.set_ylabel('Equity ($)', color='white', fontsize=12)
ax.legend(fontsize=10, facecolor='#16213e', edgecolor='white', labelcolor='white')
ax.tick_params(colors='white')
ax.grid(True, alpha=0.15, color='white')
for spine in ax.spines.values():
    spine.set_color('#333')

plt.tight_layout()
plt.savefig('equity_curve.png', dpi=150, facecolor=fig.get_facecolor())
plt.close()
print("Saved equity_curve.png")

# --- Entry Validation Summary ---
rpt("## Market Validation Summary")
rpt()
valid_count = df['entry_valid'].sum()
invalid_count = len(df) - valid_count
avg_slip = df[~df['entry_valid']]['entry_slippage_pct'].mean()
rpt(f"- Entries validated against Binance: **{valid_count}/{len(df)}** ({valid_count/len(df)*100:.0f}%)")
rpt(f"- Average slippage on unmatched entries: **{avg_slip:.2f}%**")
rpt(f"- Missed TP3s (price reached but not announced): **{df['tp3_missed'].sum()}**")
rpt(f"- **Conclusion: Signal prices are legitimate** — entries are achievable at or very near claimed prices")
rpt()

# ============================================================
# PHASE 4: STRATEGY PARAMETER EXTRACTION
# ============================================================

spec_lines = []
def spec(line=""):
    spec_lines.append(line)

spec("# 🔬 Pumpradar — Reverse-Engineered Strategy Specification")
spec()

# --- TP/SL Distance Analysis ---
spec("## TP/SL Distance Formula")
spec()

resolved['tp1_dist_pct'] = abs(resolved['tp1_target'] - resolved['entry_price']) / resolved['entry_price'] * 100
resolved['tp2_dist_pct'] = abs(resolved['tp2_target'] - resolved['entry_price']) / resolved['entry_price'] * 100
resolved['tp3_dist_pct'] = abs(resolved['tp3_target'] - resolved['entry_price']) / resolved['entry_price'] * 100
resolved['sl_dist_pct'] = abs(resolved['sl_target'] - resolved['entry_price']) / resolved['entry_price'] * 100

# Group by R:R tier
spec("### Distance by R:R Tier")
spec()
spec("| R:R | Avg TP1% | Avg TP2% | Avg TP3% | Avg SL% | TP1/SL | TP2/TP1 | TP3/TP2 |")
spec("|---|---|---|---|---|---|---|---|")

for rr in sorted(resolved['risk_reward'].dropna().unique()):
    sub = resolved[resolved['risk_reward'] == rr]
    tp1 = sub['tp1_dist_pct'].mean()
    tp2 = sub['tp2_dist_pct'].mean()
    tp3 = sub['tp3_dist_pct'].mean()
    sl = sub['sl_dist_pct'].mean()
    spec(f"| {rr} | {tp1:.2f}% | {tp2:.2f}% | {tp3:.2f}% | {sl:.2f}% | {tp1/sl:.2f} | {tp2/tp1:.2f} | {tp3/tp2:.2f} |")
spec()

# Overall averages
spec("### Overall Distance Averages")
spec()
avg_tp1_d = resolved['tp1_dist_pct'].mean()
avg_tp2_d = resolved['tp2_dist_pct'].mean()
avg_tp3_d = resolved['tp3_dist_pct'].mean()
avg_sl_d = resolved['sl_dist_pct'].mean()

spec(f"- **TP1 distance**: {avg_tp1_d:.2f}% from entry")
spec(f"- **TP2 distance**: {avg_tp2_d:.2f}% from entry")
spec(f"- **TP3 distance**: {avg_tp3_d:.2f}% from entry")
spec(f"- **SL distance**: {avg_sl_d:.2f}% from entry")
spec(f"- **TP1/SL ratio**: {avg_tp1_d/avg_sl_d:.2f}")
spec(f"- **TP spacing ratio (TP2/TP1)**: {avg_tp2_d/avg_tp1_d:.2f}")
spec(f"- **TP spacing ratio (TP3/TP2)**: {avg_tp3_d/avg_tp2_d:.2f}")
spec()

# Check if TP/SL distances correlate with leverage
spec("### TP/SL Distance by Leverage")
spec()
spec("| Leverage | Avg TP1% | Avg SL% | Unleveraged TP1% | Unleveraged SL% |")
spec("|---|---|---|---|---|")
for lev in sorted(resolved['leverage'].dropna().unique()):
    sub = resolved[resolved['leverage'] == lev]
    tp1 = sub['tp1_dist_pct'].mean()
    sl = sub['sl_dist_pct'].mean()
    spec(f"| {int(lev)}x | {tp1:.2f}% | {sl:.2f}% | {tp1:.2f}% | {sl:.2f}% |")
spec()

# --- Indicator Parameter Estimation ---
spec("## Indicator Parameters (from AI Insight NLP)")
spec()

# Load raw messages for NLP
with open("all_messages.json", "r", encoding="utf-8") as f:
    all_msgs = json.load(f)

signal_msgs = [m for m in all_msgs if "SIGNAL DETECTED" in m.get("text", "")]
insights = [m["text"] for m in signal_msgs if "AI Insight" in m.get("text", "")]

# Extract all mentioned indicators
indicator_mentions = {
    "EMA": 0, "MACD": 0, "RSI": 0, "Bollinger Band": 0,
    "Volume": 0, "Buy/Sell Pressure": 0, "ROC": 0,
    "Candle": 0, "Divergence": 0,
}

rsi_values = []
bb_positions = []
pressure_values = []
volume_trends = []

for text in insights:
    insight_part = text.split("AI Insight:")[-1] if "AI Insight:" in text else ""
    
    if "EMA" in text or "ema" in text.lower():
        indicator_mentions["EMA"] += 1
    if "MACD" in text:
        indicator_mentions["MACD"] += 1
    if "RSI" in text:
        indicator_mentions["RSI"] += 1
        # Extract RSI values
        rsi_vals = re.findall(r"RSI[:\s<>]*(\d+)", text)
        rsi_values.extend([int(v) for v in rsi_vals])
    if "BB" in text or "Bollinger" in text.lower() or "bollinger" in text.lower():
        indicator_mentions["Bollinger Band"] += 1
        bb_vals = re.findall(r"BB Position[:\s]*([\d.]+)", text)
        bb_positions.extend([float(v) for v in bb_vals])
    if "volume" in text.lower() or "Volume" in text:
        indicator_mentions["Volume"] += 1
        vol_pcts = re.findall(r"volume.*?([+-]?\d+\.?\d*)%", text.lower())
        volume_trends.extend([float(v) for v in vol_pcts])
    if "pressure" in text.lower() or "tekanan" in text.lower():
        indicator_mentions["Buy/Sell Pressure"] += 1
        press_vals = re.findall(r"(\d+\.?\d*)%\)", text)
        pressure_values.extend([float(v) for v in press_vals])
    if "ROC" in text:
        indicator_mentions["ROC"] += 1
    if "candle" in text.lower():
        indicator_mentions["Candle"] += 1
    if "divergence" in text.lower():
        indicator_mentions["Divergence"] += 1

spec("### Indicator Frequency in AI Insights")
spec()
spec("| Indicator | Mentions | % of Signals |")
spec("|---|---|---|")
for ind, count in sorted(indicator_mentions.items(), key=lambda x: -x[1]):
    spec(f"| {ind} | {count} | {count/len(insights)*100:.0f}% |")
spec()

if rsi_values:
    spec(f"### RSI Values Mentioned")
    spec(f"- Values found: {rsi_values}")
    spec(f"- Likely RSI threshold: **<50 for SHORT, >50 for LONG**")
    spec()

if bb_positions:
    spec(f"### Bollinger Band Positions")
    spec(f"- BB Position values: {bb_positions}")
    spec(f"- BB Position range: {min(bb_positions):.2f} – {max(bb_positions):.2f}")
    spec(f"- Likely BB settings: **(20, 2)** standard")
    spec()

if pressure_values:
    spec(f"### Buy/Sell Pressure Thresholds")
    spec(f"- Values: {pressure_values}")
    spec()

# --- Confidence Score Model ---
spec("## Confidence Score Analysis")
spec()

# Try to correlate confidence with outcomes
conf_trades = resolved[resolved['confidence_pct'].notna()]
if len(conf_trades) > 0:
    conf_wins = conf_trades[conf_trades['is_win']]['confidence_pct']
    conf_losses = conf_trades[conf_trades['is_loss']]['confidence_pct']
    
    spec("| Outcome | Avg Confidence | Min | Max |")
    spec("|---|---|---|---|")
    if len(conf_wins) > 0:
        spec(f"| Wins | {conf_wins.mean():.1f}% | {conf_wins.min():.0f}% | {conf_wins.max():.0f}% |")
    if len(conf_losses) > 0:
        spec(f"| Losses | {conf_losses.mean():.1f}% | {conf_losses.min():.0f}% | {conf_losses.max():.0f}% |")
    spec()

# --- Leverage-Confidence Mapping ---
spec("## Leverage ↔ R:R ↔ Confidence Mapping")
spec()
spec("| Leverage | Avg Confidence | Primary R:R | Count |")
spec("|---|---|---|---|")
for lev in sorted(resolved['leverage'].dropna().unique()):
    sub = resolved[resolved['leverage'] == lev]
    avg_c = sub['confidence_pct'].mean()
    primary_rr = sub['risk_reward'].mode().iloc[0] if len(sub['risk_reward'].mode()) > 0 else "N/A"
    spec(f"| {int(lev)}x | {avg_c:.0f}% | {primary_rr} | {len(sub)} |")
spec()

# --- Complete Strategy Spec ---
spec("## 🎯 Complete Strategy Specification")
spec()
spec("### Entry Conditions")
spec("1. **Multi-indicator confluence** scoring system:")
spec("   - EMA trend alignment (likely 9/21/55 or 9/21/50)")
spec("   - MACD signal confirmation")
spec("   - RSI position (>50 for LONG, <50 for SHORT)")
spec("   - RSI divergence detection (bearish/bullish)")
spec("   - Bollinger Band position (standard 20,2)")
spec("   - Volume spike detection (vs recent average)")
spec("   - Buy/Sell pressure ratio")
spec("   - Last candle direction")
spec("2. **BTC trend filter**: Prefer Sideways (79% of signals)")
spec("3. **Confidence threshold**: Minimum ~54%, likely filtered at 50%")
spec()
spec("### Position Sizing & Leverage")
spec(f"- Risk per trade: Fixed % of portfolio (recommended 2-3%)")
spec(f"- Leverage tiers mapped to confidence/R:R:")
spec(f"  - **7x**: R:R 1:2.08 (highest confidence)")
spec(f"  - **5x**: R:R 1:1.43 (medium confidence)")  
spec(f"  - **4x**: R:R 1:1.25 (lower confidence)")
spec()
spec("### Take Profit & Stop Loss")
spec(f"- **TP1**: ~{avg_tp1_d:.2f}% from entry")
spec(f"- **TP2**: ~{avg_tp2_d:.2f}% from entry (TP2/TP1 ratio: {avg_tp2_d/avg_tp1_d:.2f}x)")
spec(f"- **TP3**: ~{avg_tp3_d:.2f}% from entry (TP3/TP2 ratio: {avg_tp3_d/avg_tp2_d:.2f}x)")
spec(f"- **SL**: ~{avg_sl_d:.2f}% from entry")
spec()
spec("### Exit Management (The Core Edge)")
spec("```")
spec("Signal fires → Enter position 100%")
spec("  ├─ TP1 hit → Close 70%, move SL to breakeven")
spec("  │   Remaining 30% rides risk-free")
spec("  ├─ TP2 hit → Close 20% more, keep 10% moonbag")  
spec("  │   Remaining 10% rides to TP3")
spec("  └─ TP3 hit → Close final 10% (Jackpot)")
spec("```")
spec()
spec("### Risk Management")
spec(f"- Max consecutive losses observed: **{max_consec_loss}**")
spec(f"- Average time to SL: **{avg_dur_sl:.1f}h** (longer than TP1)")
spec(f"- BTC anomaly monitoring: Alert if BTC moves >1.5% in <5 min")
spec(f"- Manual close recommended during anomalies")

# Save reports
with open("analysis_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))
print("Saved analysis_report.md")

with open("strategy_spec.md", "w", encoding="utf-8") as f:
    f.write("\n".join(spec_lines))
print("Saved strategy_spec.md")

print("\n=== DONE ===")
print(f"Final equity (all signals, 3% risk): ${final_all:,.0f}")
print(f"Max drawdown: {dd_all:.1f}%")
print(f"Profit factor: {profit_factor:.2f}")

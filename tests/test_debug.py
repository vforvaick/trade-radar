#!/usr/bin/env python3
import sys
print(f"[1] Python started: {sys.version}", flush=True)

print("[2] Importing pandas...", flush=True)
import pandas as pd
print(f"[2] Pandas imported: {pd.__version__}", flush=True)

print("[3] Reading CSV...", flush=True)
df = pd.read_csv('validated_ledger.csv')
print(f"[3] CSV loaded: {len(df)} rows, {len(df.columns)} cols", flush=True)

print("[4] Filtering resolved trades...", flush=True)
resolved = df[df['status'] != 'OPEN'].copy()
print(f"[4] Resolved: {len(resolved)} trades", flush=True)

print("[5] Running simulation...", flush=True)
equity = 1000.0
for i, (_, row) in enumerate(resolved.sort_values('date_signal').iterrows()):
    risk = equity * 0.03
    if row['status'] == 'SL_CLOSED':
        equity -= risk
    elif row['tp1_hit']:
        entry = row['entry_price']
        sl = row['sl_target']
        tp1 = row['tp1_target']
        if pd.isna(sl) or pd.isna(entry) or pd.isna(tp1):
            continue
        sl_d = abs(sl - entry) / entry
        tp1_d = abs(tp1 - entry) / entry
        gain = risk * (tp1_d / sl_d) * 0.70
        if row['tp2_hit'] and not pd.isna(row['tp2_target']):
            tp2_d = abs(row['tp2_target'] - entry) / entry
            gain += risk * (tp2_d / sl_d) * 0.20
        if row['tp3_hit'] and not pd.isna(row['tp3_target']):
            tp3_d = abs(row['tp3_target'] - entry) / entry
            gain += risk * (tp3_d / sl_d) * 0.10
        equity += gain
    print(f"  Trade {i+1}/{len(resolved)}: {row['symbol']} {row['status']} -> equity=${equity:.0f}", flush=True)

print(f"\n[DONE] Final equity: ${equity:,.0f} ({(equity/1000-1)*100:+.1f}%)", flush=True)

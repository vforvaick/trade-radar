"""Corrected equity simulation using proper R:R-based position sizing."""
import pandas as pd

df = pd.read_csv('validated_ledger.csv')
resolved = df[df['status'] != 'OPEN'].copy().sort_values('date_signal')

def simulate(trades, risk_pct=3.0):
    equity = 1000.0
    peak = equity
    max_dd = 0
    for _, row in trades.iterrows():
        risk_amount = equity * (risk_pct / 100)
        if row['status'] == 'SL_CLOSED':
            equity -= risk_amount
        elif row['tp1_hit']:
            entry = row['entry_price']
            sl = row['sl_target']
            tp1 = row['tp1_target']
            tp2 = row['tp2_target']
            tp3 = row['tp3_target']
            if pd.isna(sl) or pd.isna(entry) or pd.isna(tp1):
                continue
            sl_d = abs(sl - entry) / entry
            tp1_d = abs(tp1 - entry) / entry
            gain = risk_amount * (tp1_d / sl_d) * 0.70
            if row['tp2_hit'] and not pd.isna(tp2):
                tp2_d = abs(tp2 - entry) / entry
                gain += risk_amount * (tp2_d / sl_d) * 0.20
            if row['tp3_hit'] and not pd.isna(tp3):
                tp3_d = abs(tp3 - entry) / entry
                gain += risk_amount * (tp3_d / sl_d) * 0.10
            equity += gain
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)
    return equity, max_dd

filters = {
    "All signals": resolved,
    "SHORT only": resolved[resolved['direction'] == 'SHORT'],
    "4x lev only": resolved[resolved['leverage'] == 4],
    "Skip Wed+Fri": resolved[~resolved['date_signal'].apply(lambda d: pd.to_datetime(d).day_name()).isin(['Wednesday', 'Friday'])],
}

for name, sub in filters.items():
    if len(sub) > 0:
        eq, dd = simulate(sub)
        print(f"{name}: ${eq:,.0f} ({(eq/1000-1)*100:+.1f}%, DD: {dd:.1f}%, trades: {len(sub)})")

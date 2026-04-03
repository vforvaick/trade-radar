import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import pytz
import warnings

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Load parsed trades
df = pd.read_csv("trade_ledger.csv")

def parse_date(date_str):
    if pd.isna(date_str):
        return None
    dt = datetime.fromisoformat(date_str)
    return int(dt.timestamp() * 1000)

def format_date(ts):
    if not ts: return None
    return datetime.fromtimestamp(ts/1000, tz=pytz.UTC).isoformat()

def get_klines(symbol, start_ts, end_ts):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 1500
    }
    r = requests.get(url, params=params, verify=False)
    if r.status_code != 200:
        raise Exception(f"API Error {r.status_code}: {r.text}")
    return r.json()

results = []

print(f"Validating {len(df)} trades against Binance market data...")

for i, row in df.iterrows():
    symbol = row['symbol']
    direction = row['direction']
    sig_date = parse_date(row['date_signal'])
    
    start_ts = sig_date - (5 * 60 * 1000) # 5 mins before
    
    close_dates = [row['tp3_date'], row['tp2_date'], row['tp1_date'], row['sl_date']]
    close_dates = [parse_date(d) for d in close_dates if not pd.isna(d)]
    
    end_ts = max(close_dates) + (5 * 60 * 1000) if close_dates else sig_date + (48 * 60 * 60 * 1000)
    
    try:
        print(f"[{i+1}/{len(df)}] Fetching {symbol}...")
        klines = get_klines(symbol, start_ts, end_ts)

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        # Mark as invalid
        row['entry_valid'] = False
        results.append(row)
        continue
    
    # Find entry validity
    # Was the claimed entry price reached within 15 minutes AFTER the signal?
    entry_target = row['entry_price']
    entry_valid = False
    entry_hit_timestamp = None
    
    for k in klines:
        ts, open_p, high_p, low_p, close_p = k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4])
        
        # Check if right after signal
        if ts >= sig_date and ts <= sig_date + (15 * 60 * 1000):
            if low_p <= entry_target <= high_p:
                entry_valid = True
                entry_hit_timestamp = ts
                break
    
    # If not exactly valid, what was the actual open price at the exact signal minute?
    signal_actual_price = None
    for k in klines:
        ts = k[0]
        if ts >= sig_date and ts < sig_date + 60000:
            signal_actual_price = float(k[1])
            break
            
    slippage_pct = 0
    if not entry_valid and signal_actual_price:
        slippage_pct = abs(signal_actual_price - entry_target) / entry_target * 100
        
    row['entry_valid'] = entry_valid
    row['actual_signal_price'] = signal_actual_price
    row['entry_slippage_pct'] = slippage_pct
    
    # Verify exact TP3 hits even if not announced
    tp3_missed = False
    tp3_target = row['tp3_target']
    
    if not pd.isna(tp3_target) and row['status'] in ['TP1', 'TP2']:
        # Check if TP3 was ever hit after the signal
        for k in klines:
            ts, high_p, low_p = k[0], float(k[2]), float(k[3])
            if ts > sig_date:
                if (direction == 'LONG' and high_p >= tp3_target) or \
                   (direction == 'SHORT' and low_p <= tp3_target):
                    tp3_missed = True
                    row['actual_tp3_hit_time'] = format_date(ts)
                    row['status'] = 'TP3_MISSED'  # Update status
                    break
                    
    row['tp3_missed'] = tp3_missed
    
    # TODO: We can do much deeper validation of all SL/TP timestamps
    
    results.append(row)
    time.sleep(0.1)  # Rate limit safety

val_df = pd.DataFrame(results)
val_df.to_csv("validated_ledger.csv", index=False)

print("\nValidation Complete!")
print("Entry Validity Summary:")
print(val_df['entry_valid'].value_counts())
print("\nAverage slippage on invalid entries:", val_df[~val_df['entry_valid']]['entry_slippage_pct'].mean(), "%")
print("\nMissed TP3s detected:", val_df['tp3_missed'].sum())

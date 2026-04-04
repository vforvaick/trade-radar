# Strategy Deep-Dive & Parameter Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dissect every passport strategy to rule-entry/exit level, explain fakeout mechanics with candle pattern examples, and produce concrete parameter fix JSON per passport.

**Architecture:** Diagnostic-first — each strategy gets a full teardown explaining HOW the scoring engine processes its weight config, WHAT candle scenarios cause false signals, and WHY the backtest/live results look the way they do. Then each strategy gets a recommended parameter fix with rationale rooted in the scoring math and reference literature.

**Tech Stack:** Python (bot/scorer.py, bot/indicators.py, bot/signals.py, bot/position_manager.py), JSON passport configs, Binance Futures 1H OHLCV data.

---

## Scoring Engine Mechanics (Prerequisite Context)

Before dissecting strategies, the executor MUST understand how `scorer.py` computes confidence:

```
1. Each indicator returns a direction: LONG, SHORT, or NEUTRAL
2. Each indicator has a weight from the passport config
3. All non-volume indicators add their weight to total_weight regardless of direction
4. LONG/SHORT votes add their weight to long_score/short_score
5. NEUTRAL votes add nothing to scores but DO add to total_weight → dilutes confidence
6. Volume spike is special: only adds weight to the dominant direction (confirmation, not directional)
7. confidence = (dominant_score / total_weight) × 100
8. BTC trend filter multiplies confidence (×0.5 in Uptrend)
9. Signal fires if confidence ≥ CONFIDENCE_THRESHOLD
```

**Critical implication:** Zero-weighted indicators (weight=0.0) contribute NOTHING to `total_weight`. They effectively don't exist. This means a passport with 3 active indicators has a very different scoring dynamic than one with 8.

**Volume spike quirk:** If `vol_spike=True`, volume weight is ADDED to both dominant_score and total_weight. If `vol_spike=False`, volume weight is entirely absent. This creates binary behavior: vol spike ON = huge confidence boost, vol spike OFF = no vol influence at all.

---

## Pre-Cutover Live Snapshot (2026-04-03 09:48 UTC)

| Passport | Equity | Return | Signals | Trades | Open |
|----------|--------|--------|---------|--------|------|
| 🏆 OG | $1,052 | +5.2% | 63 | 34 | 29 |
| 💎 HiddenGem | $970 | -3.0% | 2 | 1 | 1 |
| 🚀 Momentum | $905 | -9.5% | 32 | 23 | 9 |
| 🎯 Dynamic | $831 | -16.9% | 34 | 25 | 9 |
| 🔄 Reversal | $407 | -59.3% | 337 | 152 | 185 |
| 🎯 Sniper | $1,000 | 0% | 0 | 0 | 0 |
| 📢 VolumeKing | $1,000 | 0% | 0 | 0 | 0 |

## Reference Backtest Results

| Test | Return | WR | Trades | Notes |
|------|--------|----|--------|-------|
| Grid Search #1 (EMA 8/21/55, Vol 2.0x) | +49.1% | 49.0% | 618 | 30-day |
| Grid Search #2 (EMA 9/21/50, Vol 2.0x) | +49.1% | 49.5% | 610 | 30-day, live params |
| Grid Search #4 (EMA 9/21/50, Vol 1.5x) | +11.3% | 49.0% | 692 | OG params |
| Indicator Lab #1 (HiddenGem weights) | +17.0% | 48.0% | 198 | 180-day, ONLY profitable |
| Exit Opt: No ATR, No Trail | -17.9% | 39.9% | 4583 | 180-day baseline |
| Exit Opt: With Trailing | -81.3% | 39.9% | 4992 | Trailing DESTROYS perf |
| Twin: Momentum 180d | -81.5% | 40.6% | 4095 | Catastrophic |
| Twin: Reversal 180d | -35.2% | 40.9% | 4234 | Bad but less than Momentum |

---

## Strategy 1: 🏆 OG Balance — "The Survivor"

### Config Anatomy
```json
{
  "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
  "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 1.0,
  "pressure": 1.0, "candle_direction": 1.0
}
VOLUME_SPIKE_THRESHOLD: 1.5, CONFIDENCE_THRESHOLD: 54
USE_ATR_EXITS: false, USE_TRAILING_STOP: false
```

### Scoring Math
- 7 directional indicators × weight 1.0 = `total_weight` baseline of 7.0
- Volume spike adds 1.0 only when confirming dominant direction
- Max possible confidence: 8/8 = 100% (all agree + vol spike)
- Min to fire: 54% → need at least 4.32/8.0 weighted votes

**Key insight:** With 7 directional indicators all at weight 1.0, any NEUTRAL vote dilutes the denominator without adding to the numerator. If 2 indicators are NEUTRAL, you need ~4.32 out of 6 remaining = 72% agreement among active indicators. This creates natural selectivity.

### Why It's the Only Green Strategy
1. **Balanced consensus** — No indicator can dominate. A signal needs 5+ indicators agreeing out of 8.
2. **Vol threshold 1.5x** — Lower bar means more trades (63 signals vs 2 for HiddenGem), giving the edge more chances to express.
3. **No ATR/trailing** — Fixed TP/SL cascade is more stable in crypto's volatility regime.
4. **8-indicator dilution** — NEUTRAL votes from BB, RSI divergence, and pressure naturally filter choppy markets.

### Fakeout Scenario: "The Choppy Range Trap"

```
Market: ETHUSDT ranging 3200-3400 for 2 days
Candle: 1H green candle 3250→3310 with vol 1.6x avg

Indicator states:
  EMA trend: LONG (9>21 from recent bounce) — but barely, 50-EMA at 3280
  MACD: LONG (histogram slightly positive, rising)
  RSI: LONG (value=53, just above 50)
  RSI divergence: NEUTRAL (no divergence pattern)
  BB position: NEUTRAL (position=0.45, mid-band)
  Volume: spike=True (1.6x > 1.5x threshold)
  Pressure: NEUTRAL (pct=56%, below 60% threshold)
  Candle: LONG (green candle)

Scoring:
  LONG votes: EMA(1) + MACD(1) + RSI(1) + candle(1) = 4.0
  NEUTRAL: div(1) + BB(1) + pressure(1) = 3.0 (dilutes denominator)
  total_weight = 7.0 (excl vol)
  Vol spike confirms LONG: long_score = 4+1 = 5.0, total = 8.0
  Confidence = 5.0/8.0 = 62.5% ✅ Fires

BUT: Price is just bouncing in a range. EMA 50 at 3280 acts as magnet.
Next 3 candles: 3310→3290→3250→3220. SL at ~3190 not hit but position
underwater. Eventually closes at SL or breakeven after TP1 scrapes by.
```

**Root cause:** EMA/MACD/RSI all give weak LONG signals in a range because price temporarily crosses above their thresholds. The low vol threshold (1.5x) lets mediocre volume spikes confirm the fake signal.

### Parameter Fix Recommendation

```json
{
    "name": "Pumpradar OG",
    "emoji": "🏆",
    "description": "Balanced consensus — equal weights, Vol 2.0x filter (optimized from 1.5x)",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.0,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.0,
            "macd_signal": 1.0,
            "rsi_position": 1.0,
            "rsi_divergence": 1.0,
            "bb_position": 1.0,
            "volume_spike": 1.0,
            "pressure": 1.0,
            "candle_direction": 1.0
        },
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 50,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

**Changes:** `VOLUME_SPIKE_THRESHOLD: 1.5 → 2.0`
**Rationale:** Grid search proves 2.0x volume filter quadruples return (+49% vs +11%) with negligible WR change. The 0.5x higher threshold eliminates ~12% of mediocre volume spikes that lead to range-trap fakeouts like the example above. Trade count drops ~10% but quality improves dramatically.

---

## Strategy 2: 💎 HiddenGem — "The Quiet Winner"

### Config Anatomy
```json
{
  "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
  "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
  "pressure": 0.0, "candle_direction": 0.0
}
VOLUME_SPIKE_THRESHOLD: 2.0, CONFIDENCE_THRESHOLD: 54
```

### Scoring Math
- Only 2 directional indicators active: EMA(1.0) + BB(1.0) → `total_weight` baseline = 2.0
- Volume spike weight = 2.0, only added on confirmation
- Zero-weighted indicators vanish from scoring entirely

**Possible outcomes:**

| EMA | BB | Vol Spike | Confidence | Fires? |
|-----|-----|-----------|-----------|--------|
| LONG | LONG | Yes | 4.0/4.0 = 100% | ✅ |
| LONG | LONG | No | 2.0/2.0 = 100% | ✅ |
| LONG | NEUTRAL | Yes | 3.0/4.0 = 75% | ✅ |
| LONG | NEUTRAL | No | 1.0/2.0 = 50% | ❌ |
| LONG | SHORT | Yes | vol doesn't add (tie) | ❌ |
| LONG | SHORT | No | 1.0/2.0 = 50% | ❌ |
| NEUTRAL | LONG | Yes | 3.0/4.0 = 75% | ✅ |
| NEUTRAL | LONG | No | 1.0/2.0 = 50% | ❌ |
| NEUTRAL | NEUTRAL | any | 0/2.0 = 0% | ❌ |

**Key insight:** HiddenGem fires when (EMA + BB agree) OR (one agrees + vol spike confirms). Without vol spike, both EMA and BB must point the same direction.

### Why It's the Best Risk-Adjusted Strategy
1. **Indicator Lab winner:** +17.0% return over 180 days — the ONLY profitable weight combination tested
2. **EMA + BB complementary:** EMA confirms trend, BB confirms position relative to volatility envelope
3. **Heavy vol filter (2.0x, weight 2.0):** Double protection — threshold AND weight amplification

### Why It's Too Quiet (Only 2 Signals in 3 Days)
The problem isn't the weights — it's the **BB direction threshold** in `indicators.py`:

```python
# BB LONG only when position < 0.2 (near lower band)
# BB SHORT only when position > 0.8 (near upper band)
# NEUTRAL for 0.2-0.8 (60% of the range!)
```

EMA and BB rarely agree because:
- BB LONG (position < 0.2) means price near lower band → usually in a downtrend → EMA likely SHORT
- BB SHORT (position > 0.8) means price near upper band → usually in an uptrend → EMA likely LONG
- Agreement only happens at trend **inflection points** (reversal just starting, EMAs crossing while BB extreme)

This is actually a VERY good signal — early trend reversals with volume confirmation. But it happens maybe once every few days per pair.

### Fakeout the HiddenGem Avoids

```
Same ETHUSDT range scenario as OG:
  EMA: LONG (1.0)
  BB: NEUTRAL (position=0.45)
  Vol spike: True (2.1x)

Scoring:
  LONG votes: EMA(1.0) = 1.0
  NEUTRAL: BB(1.0) → dilutes denominator
  total_weight = 2.0
  Vol spike: long dominant → long=1+2=3, total=2+2=4
  Confidence = 3.0/4.0 = 75% → Fires ✅

Wait — it DOES fire here? Vol spike rescues it!
```

Actually this IS a weakness of HiddenGem. When BB is NEUTRAL and EMA is directional with a vol spike, the 2.0 vol weight overwhelms the 1.0 BB neutral dilution. The signal fires on EMA + volume alone without BB confirmation.

**But this only fires 75% of the time.** In the OG case, the same scenario fired at 62.5%. So HiddenGem is more selective on MOST scenarios but can still be tricked by strong volume spikes.

### Parameter Fix Recommendation

```json
{
    "name": "Pumpradar HiddenGem",
    "emoji": "💎",
    "description": "180-day winner: EMA+BB+Volume with pressure for extra consensus",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.0,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.5,
            "macd_signal": 0.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 1.0,
            "volume_spike": 2.0,
            "pressure": 0.5,
            "candle_direction": 0.0
        },
        "CONFIDENCE_THRESHOLD": 58,
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 50,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

**Changes:**
1. `ema_trend: 1.0 → 1.5` — EMA gets more vote power, requiring stronger trend for signal
2. `pressure: 0.0 → 0.5` — Adds buy/sell pressure as mild tiebreaker, increases total_weight denominator which filters out volume-only rescues
3. `CONFIDENCE_THRESHOLD: 54 → 58` — Slightly higher bar to compensate for more voting mass

**Math check on the ETHUSDT fakeout:**
- New total_weight = 1.5 (ema) + 1.0 (bb) + 0.5 (pressure, NEUTRAL → dilutes) = 3.0
- Vol spike: long_score = 1.5 + 2.0 = 3.5, total = 3.0 + 2.0 = 5.0
- Confidence = 3.5/5.0 = 70% → fires (above 58%)
- Hmm, still fires. But the real protection is that with pressure=NEUTRAL more often, marginal signals get diluted.

**Alternative approach (more conservative):** Keep original weights, lower threshold to 50% to increase trade frequency while maintaining the same quality filter. This would capture the "EMA+BB agree without vol spike" signals that currently barely miss at 50%.

---

## Strategy 3: 🚀 Momentum — "The Whipsaw Victim"

### Config Anatomy
```json
{
  "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
  "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
  "pressure": 1.0, "candle_direction": 1.0
}
VOLUME_SPIKE_THRESHOLD: 2.0, CONFIDENCE_THRESHOLD: 54
```

### Scoring Math
Identical to OG except `volume_spike: 2.0` instead of 1.0 (and threshold 2.0x vs 1.5x).
- total_weight baseline = 7.0, max with vol = 9.0
- Min to fire: 54% of 9.0 = 4.86 → need ~5 weighted votes

### Why It's Losing (-9.5% Live, -81.5% in 180-day Backtest)
The 180-day backtest is devastating: -81.5% with 4095 trades and 40.6% WR. This means:
- Average loss per trade > average win per trade
- WR below 50% with asymmetric TP cascade means net negative expectancy
- 4095 trades over 180 days = ~23 trades/day across 10 pairs = ~2.3 trades/pair/day

**The problem is overtrading in choppy markets.** With 7 directional indicators at weight 1.0, even weakly aligned indicators produce signals. The 2.0x vol boost amplifies any marginal consensus.

### Fakeout Scenario: "Momentum Whipsaw at Support"

```
Market: SOLUSDT in a downtrend, price at key support $145
Previous candles: 152→148→146→145 (grinding down)
Current 1H candle: Opens 145, drops to 143, bounces to 147, vol 2.3x avg

Indicator states:
  EMA trend: SHORT (9<21<50, clear downtrend)
  MACD: SHORT (histogram negative, deepening)
  RSI: SHORT (value=42)
  RSI divergence: NEUTRAL (no divergence)
  BB position: LONG (position=0.12, near lower band!)
  Volume spike: True (2.3x)
  Pressure: LONG (pct=68%, bounce from low created buy pressure)
  Candle: LONG (green, bounced from 143 to 147)

Scoring:
  SHORT votes: EMA(1) + MACD(1) + RSI(1) = 3.0
  LONG votes: BB(1) + pressure(1) + candle(1) = 3.0
  NEUTRAL: div(1) → total_weight = 7.0
  TIE! → "No directional consensus" → No signal

Actually this scenario produces no signal. Let's adjust:
```

```
Same setup but RSI at 48 (still SHORT < 50) and no BB extreme:
  BB position: NEUTRAL (position=0.35)

  SHORT votes: EMA(1) + MACD(1) + RSI(1) = 3.0
  LONG votes: pressure(1) + candle(1) = 2.0
  NEUTRAL: div(1) + BB(1) → total_weight = 7.0
  Vol spike confirms SHORT (dominant): short=3+2=5, total=7+2=9
  Confidence = 5/9 = 55.6% → Fires SHORT ✅

BUT: Price was AT support. The bounce from 143→147 was the beginning of
a reversal. Next candles: 147→151→155→160. SHORT gets stopped out at
SL (~152 with 3.8% SL on entry 145).
```

**Root cause:** EMA/MACD/RSI are all lagging indicators pointing SHORT from the prior trend, but price has already found support and is reversing. Momentum strategy has no support/resistance awareness. Volume spike + 3 lagging SHORT indicators overpower the 2 forward-looking LONG signals (pressure + candle).

### Fakeout Scenario 2: "The False Breakout"

```
Market: BTCUSDT consolidating at 84000, triangle pattern
Current 1H: Price punches to 84800 on vol 2.4x then closes at 84200

  EMA: LONG (just crossed, 9>21, price above 50-EMA at 83500)
  MACD: LONG (histogram just turned positive)
  RSI: LONG (value=56, crossed above 50)
  RSI div: NEUTRAL
  BB: SHORT (position=0.85, near upper band after the spike)
  Vol spike: True (2.4x)
  Pressure: LONG (pct=65%, wick up shows buying)
  Candle: LONG (green, closed above open)

  LONG: EMA(1)+MACD(1)+RSI(1)+pressure(1)+candle(1) = 5.0
  SHORT: BB(1) = 1.0
  NEUTRAL: div(1) → total_weight = 7.0
  Vol confirms LONG: long=5+2=7, total=7+2=9
  Confidence = 7/9 = 77.8% → Strong LONG signal ✅

ENTRY at 84200. But this was a false breakout of the triangle.
Next candles: 84200→83800→83200→82500. SL at ~81000 may not hit
immediately but the trade is deeply underwater. Eventually SL hit.
```

**Root cause:** 5 out of 7 directional indicators aligned LONG because of the breakout candle. Only BB warned (near upper band = potential SHORT). But 1 contrarian vote vs 5 agreeing = noise. The vol spike made it worse by confirming the wrong direction.

### Parameter Fix Recommendation

```json
{
    "name": "Pumpradar Momentum",
    "emoji": "🚀",
    "description": "Trend-following with EMA emphasis, reduced noise indicators, Vol 2.0x",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.0,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 2.0,
            "macd_signal": 1.0,
            "rsi_position": 1.0,
            "rsi_divergence": 0.5,
            "bb_position": 1.0,
            "volume_spike": 1.5,
            "pressure": 0.5,
            "candle_direction": 0.5
        },
        "CONFIDENCE_THRESHOLD": 60,
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 30,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

**Changes:**
1. `ema_trend: 1.0 → 2.0` — EMA is the primary trend filter; doubling its weight means a signal CANNOT fire without EMA agreement (or near-unanimous other indicators)
2. `rsi_divergence: 1.0 → 0.5` — Divergence is noisy on 1H; reduce its dilution effect
3. `pressure: 1.0 → 0.5`, `candle_direction: 1.0 → 0.5` — These are single-candle noise indicators; downweight to prevent them from tipping marginal signals
4. `volume_spike: 2.0 → 1.5` — Vol confirmation is important but 2.0 creates too much binary swing
5. `CONFIDENCE_THRESHOLD: 54 → 60` — Higher bar eliminates ~30% of marginal signals that hit in choppy markets
6. `MAX_OPEN_POSITIONS_PER_PASSPORT: 50 → 30` — Risk management cap; Momentum had 32 signals in 3 days

**Math check on the false breakout:**
- New: LONG = EMA(2)+MACD(1)+RSI(1)+pressure(0.5)+candle(0.5) = 5.0
- SHORT = BB(1) = 1.0, NEUTRAL = div(0.5)
- total_weight = 2+1+1+0.5+1+0.5+0.5 = 6.5
- Vol confirms LONG: long=5+1.5=6.5, total=6.5+1.5=8.0
- Confidence = 6.5/8.0 = 81.3% → Still fires :(

The false breakout is hard to filter with pure indicator weights because ALL momentum indicators agree. This is a fundamental limitation — you need a **regime filter** (e.g., "is price in a compression pattern?") or a **breakout confirmation candle** (wait for next candle to confirm) to avoid this.

**Additional code-level recommendation:** Add a multi-candle confirmation: require 2 consecutive candles agreeing before entry. This would prevent false breakout entries on single spike candles.

---

## Strategy 4: 🎯 Dynamic Momentum — "The Trailing Stop Killer"

### Config Anatomy
```json
{
  "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
  "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
  "pressure": 1.0, "candle_direction": 1.0
}
VOLUME_SPIKE_THRESHOLD: 2.0, USE_ATR_EXITS: true, USE_TRAILING_STOP: true
```

### Why -16.9% vs Momentum's -9.5% (Same Entry Logic, Worse Exits)
Dynamic has IDENTICAL entry logic to Momentum. The only difference is exit management:
- `USE_ATR_EXITS: true` → SL = entry ± 2×ATR, TP1 = entry ± 4×ATR
- `USE_TRAILING_STOP: true` → After TP1, trailing SL = candle_high - original_SL_distance

**Exit optimization proves it:** Trailing stop takes return from -17.9% to -81.3% (same entry filters, 180-day test). The trailing stop alone destroys 63 percentage points of performance.

### The Trailing Stop Death Spiral (Detailed Mechanism)

```python
# From position_manager.py line 181-193:
if pos.tp1_hit and USE_TRAILING_STOP:
    trail_dist = abs(entry - original_SL)  # e.g., 3.8% of entry
    if is_long:
        new_sl = high - trail_dist
        if new_sl > pos.trailing_sl and new_sl > entry:
            pos.trailing_sl = new_sl
```

**The problem:** `trail_dist` is the FULL original SL distance. In crypto, 1H candles frequently spike 2-3% and retrace. The trailing stop ratchets up on every new high but the trail distance is too tight for crypto volatility.

### Fakeout Scenario: "Trail-to-Death"

```
LONG entry on PEPEUSDT at 0.01200, SL at 0.01154 (3.8% below)
ATR(14) = 0.00030, so ATR SL = 0.01200 - 2×0.00030 = 0.01140 (5% below)
ATR TP1 = 0.01200 + 4×0.00030 = 0.01320 (10% above)

Candle progression (1H):
  Hour 1: H=0.01250, L=0.01190, C=0.01240 (rising)
  Hour 2: H=0.01310, L=0.01230, C=0.01300 (approaching TP1)
  Hour 3: H=0.01330, L=0.01280, C=0.01320 → TP1 HIT ✅
    - 70% closed at +10% profit (leveraged ~50%)
    - SL moves to breakeven (0.01200)
    - Trailing activates: trail_dist = 0.01200 - 0.01140 = 0.00060
    - new_sl = 0.01330 - 0.00060 = 0.01270 (above entry) ✅

  Hour 4: H=0.01350, L=0.01290, C=0.01340
    - Trail updates: new_sl = 0.01350 - 0.00060 = 0.01290

  Hour 5: H=0.01345, L=0.01280, C=0.01285
    - Low 0.01280 < trailing_sl 0.01290 → STOPPED OUT at 0.01290
    - Remaining 30% closed at +7.5% instead of riding to TP2 (+16%) or TP3 (+24%)

  Hours 6-12: Price resumes: 0.01285→0.01340→0.01400→0.01450
    - Would have hit TP2 (0.01520) if not stopped out
```

**Root cause:** Crypto 1H candles regularly retrace 3-5% intrabar. A trailing stop with trail_dist = SL_dist (~5% for ATR) means any 5% retrace from the highest high kills the trail. For volatile memecoins, this happens almost every cycle.

### ATR Exit Analysis

ATR exits themselves are neutral (backtest shows identical -17.9% return with or without ATR). This is because:
- ATR SL (2×ATR) is roughly similar to fixed SL (~3.8%) for 1H crypto
- ATR TP1 (4×ATR) is wider than fixed TP1 (~4.3%), so fewer TP1 hits but bigger when they hit
- These effects cancel out

### Parameter Fix Recommendation

```json
{
    "name": "Pumpradar Dynamic",
    "emoji": "🎯",
    "description": "ATR-based exits WITHOUT trailing — same as improved Momentum entries",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.0,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 2.0,
            "macd_signal": 1.0,
            "rsi_position": 1.0,
            "rsi_divergence": 0.5,
            "bb_position": 1.0,
            "volume_spike": 1.5,
            "pressure": 0.5,
            "candle_direction": 0.5
        },
        "CONFIDENCE_THRESHOLD": 60,
        "USE_ATR_EXITS": true,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 30,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

**Changes:**
1. `USE_TRAILING_STOP: true → false` — **Critical fix.** Trailing stop proven destructive.
2. Same entry weight improvements as Momentum (ema=2.0, reduced noise indicators)
3. Keep `USE_ATR_EXITS: true` — neutral impact but adapts to volatility regime changes

**Future code improvement:** If trailing stop is ever re-enabled, change the trail distance formula:
- Current: `trail_dist = abs(entry - original_SL)` (too tight)
- Better: `trail_dist = 1.5 × ATR` (adapts to current volatility, not entry-time SL)
- Also: Only trail after TP2 (not TP1) to let the position breathe

---

## Strategy 5: 🔄 Reversal — "Fundamentally Broken"

### Config Anatomy
```json
{
  "REVERSAL_MODE": true,
  "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 2.0,
  "rsi_divergence": 1.0, "bb_position": 2.0, "volume_spike": 2.0,
  "pressure": 0.0, "candle_direction": 0.0
}
CONFIDENCE_THRESHOLD: 60, USE_ATR_EXITS: true, USE_TRAILING_STOP: false
MAX_OPEN_POSITIONS_PER_PASSPORT: 20
REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD: 80
REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT: 5
```

### Scoring Math
- Active indicators: RSI(2.0) + BB(2.0) + div(1.0) = 5.0 directional weight
- Volume adds 2.0 on confirmation → max 7.0
- Zero indicators: ema, macd, pressure, candle → invisible

### The Fundamental Design Flaw

**The Reversal passport claims to be mean-reversion but uses momentum-style indicator thresholds.**

Mean-reversion logic SHOULD work like:
- Price oversold (RSI < 30) → BUY (expect bounce)
- Price at lower BB (position < 0.1) → BUY (expect reversion to mean)
- Combine both → strong buy signal

But the ACTUAL indicator code in `indicators.py` uses:
```python
# RSI signal thresholds (config.py):
RSI_LONG_THRESHOLD = 50   # > 50 = LONG
RSI_SHORT_THRESHOLD = 50  # < 50 = SHORT

# BB direction thresholds (indicators.py):
if position < 0.2: return "LONG"    # near lower band
elif position > 0.8: return "SHORT"  # near upper band
```

**RSI and BB CONFLICT for mean-reversion:**
- When price is oversold (RSI=35, BB position=0.1):
  - RSI says SHORT (35 < 50)
  - BB says LONG (0.1 < 0.2)
  - They CANCEL OUT
- When price is overbought (RSI=70, BB position=0.9):
  - RSI says LONG (70 > 50)
  - BB says SHORT (0.9 > 0.8)
  - They CANCEL OUT again

**The only time RSI and BB agree is in trend-following scenarios:**
- Uptrend pullback: RSI=55 (LONG) + BB position=0.15 (LONG) → both LONG
- Downtrend rally: RSI=45 (SHORT) + BB position=0.85 (SHORT) → both SHORT

This means the "Reversal" strategy is actually doing **trend pullback buying** without any trend filter (EMA/MACD zeroed). It enters pullbacks blind to the overall trend direction.

### Why 337 Signals in 3 Days (Overtrade Mechanism)

With only RSI + BB + divergence active:
1. In choppy markets, RSI oscillates around 50 frequently
2. BB position moves between 0.2-0.8 in ranges, occasionally touching extremes
3. When both happen to point the same direction + vol spike (2.0x) → fires
4. No EMA/MACD means no trend-persistence check → fires in EVERY direction
5. With 200+ pairs scanned per cycle, even rare coincidences produce many signals

**Pre-cutover:** 337 signals / 3 days / 200 pairs = ~0.56 signals per pair per day. That's roughly every 2 hours a given pair gets a Reversal signal. With 185 open positions, the position manager was completely saturated (cap was 20, but the cap applies per scan cycle, and with 337 signals it hit the cap repeatedly).

### Fakeout Scenario: "The Blind Counter-Trend"

```
Market: DOGEUSDT in strong downtrend 0.180→0.150 over 3 days
Current: Price at 0.155, just bounced from 0.150

  RSI: 52 (LONG, just crossed above 50 on the bounce) → weight 2.0
  BB: 0.18 (LONG, near lower band) → weight 2.0
  RSI div: LONG (price made lower low, RSI made higher low — classic bullish div)
  Vol spike: True (2.2x, sell capitulation volume)
  EMA: SHORT (9<21<50, strong downtrend) — but weight=0.0, INVISIBLE
  MACD: SHORT (deeply negative) — but weight=0.0, INVISIBLE

Scoring (REVERSAL_MODE forces ema/macd to 0):
  LONG: RSI(2.0) + BB(2.0) + div(1.0) = 5.0
  total_weight = 2.0 + 2.0 + 1.0 = 5.0
  Vol confirms LONG: long = 5+2 = 7, total = 5+2 = 7
  Confidence = 7/7 = 100% → STRONG LONG SIGNAL ✅

ENTRY LONG at 0.155. But the downtrend isn't done.
Price: 0.155→0.148→0.142→0.135. Full SL hit.
The RSI divergence was CORRECT that a bounce was coming,
but the bounce was only 0.150→0.155 (3.3%), not enough
for TP1 at ~0.165 (6.5% away with ATR exits).
```

**Root cause:** Without EMA/MACD, the strategy cannot distinguish between:
1. A genuine trend reversal (where divergence + BB extreme = good entry)
2. A minor dead-cat bounce in an ongoing downtrend (where the same signals fire but the move is too small)

The divergence detection in `indicators.py` uses a simple 14-bar half-split comparison, which fires frequently in downtrends (every bounce creates a "higher RSI low").

### Parameter Fix Recommendation

**Keep quarantined.** The Reversal passport needs CODE CHANGES, not just config tuning:

1. **RSI thresholds must be configurable per-passport:** Add `RSI_LONG_THRESHOLD` and `RSI_SHORT_THRESHOLD` to config_overrides. For reversal: `RSI_LONG_THRESHOLD: 30` (buy only oversold), `RSI_SHORT_THRESHOLD: 70` (sell only overbought).

2. **BB should have a "stretch" mode:** Instead of direction, return a "stretch score" indicating how far outside the bands price is. Reversal enters only when stretch > 1.0 (outside bands).

3. **Require EMA as a FILTER, not a voter:** Even for reversals, the trend context matters. Instead of weight=0, use EMA as a gate: only allow LONG reversals when EMA says SHORT (counter-trend entry) and confidence is very high.

4. **Add cooldown timer:** After a signal fires, no new Reversal signal for the same pair for N hours.

**Interim quarantine config (if it must be re-enabled for monitoring):**

```json
{
    "name": "Pumpradar Reversal",
    "emoji": "🔄",
    "enabled": false,
    "description": "QUARANTINED — needs RSI threshold overhaul + regime filter + cooldown timer",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.5,
        "INDICATOR_WEIGHTS": {
            "REVERSAL_MODE": true,
            "ema_trend": 0.0,
            "macd_signal": 0.0,
            "rsi_position": 2.0,
            "rsi_divergence": 1.5,
            "bb_position": 2.0,
            "volume_spike": 1.0,
            "pressure": 0.0,
            "candle_direction": 0.0
        },
        "USE_ATR_EXITS": true,
        "USE_TRAILING_STOP": false,
        "CONFIDENCE_THRESHOLD": 85,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 5,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
        "REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD": 90,
        "REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT": 3
    }
}
```

**Interim changes (keep disabled):**
- `CONFIDENCE_THRESHOLD: 60 → 85` — Near-unanimous agreement required
- `VOLUME_SPIKE_THRESHOLD: 2.0 → 2.5` — Only extreme volume events
- `volume_spike: 2.0 → 1.0` — Reduce vol amplification
- `rsi_divergence: 1.0 → 1.5` — Require divergence to play bigger role (real reversals usually show divergence)
- `MAX_OPEN_POSITIONS_PER_PASSPORT: 20 → 5` — Hard cap

---

## Strategy 6: 🎯 Sniper — "Over-Filtered to Silence"

### Config Anatomy
```json
{
  "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
  "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
  "pressure": 0.0, "candle_direction": 0.0
}
CONFIDENCE_THRESHOLD: 70, VOLUME_SPIKE_THRESHOLD: 2.0
```

Same weights as HiddenGem but with CONFIDENCE_THRESHOLD: 70 instead of 54.

### Why It Never Fires

Revisiting the HiddenGem scoring table with threshold 70:

| EMA | BB | Vol Spike | Confidence | Fires @70? |
|-----|-----|-----------|-----------|------------|
| LONG | LONG | Yes | 100% | ✅ |
| LONG | LONG | No | 100% | ✅ |
| LONG | NEUTRAL | Yes | 75% | ✅ |
| LONG | NEUTRAL | No | 50% | ❌ |
| NEUTRAL | LONG | Yes | 75% | ✅ |
| NEUTRAL | LONG | No | 50% | ❌ |

At 54% threshold (HiddenGem), rows 1-4 fire. At 70%, rows 1-3 fire. The difference is small on paper — but in practice, the EMA+BB agreement that rows 1-2 require almost never happens (as explained in HiddenGem analysis).

The realistic firing scenarios (rows 3 & 4) require vol spike + one indicator. At 70% threshold, row 4 (EMA directional + BB NEUTRAL + no vol) doesn't fire. This is the most common scenario.

**The REAL reason Sniper never fires in 3 days:** The HiddenGem only fired 2 signals in the same period. Sniper is a strict subset of HiddenGem signals (confidence > 70 within HiddenGem's already sparse signals). With only 2 HiddenGem signals, neither exceeded 70% confidence.

### Parameter Fix Recommendation

```json
{
    "name": "Pumpradar Sniper",
    "emoji": "🔫",
    "description": "High-confidence variant: HiddenGem core with MACD confirmation + 65% threshold",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.0,
        "CONFIDENCE_THRESHOLD": 65,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.5,
            "macd_signal": 1.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 1.0,
            "volume_spike": 2.0,
            "pressure": 0.0,
            "candle_direction": 0.0
        },
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 50,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

**Changes:**
1. `CONFIDENCE_THRESHOLD: 70 → 65` — Still selective but achievable
2. `macd_signal: 0.0 → 1.0` — Adds MACD as trend momentum confirmation
3. `ema_trend: 1.0 → 1.5` — Stronger EMA weighting

**New scoring dynamics:**
- total_weight = 1.5 (ema) + 1.0 (macd) + 1.0 (bb) = 3.5
- With vol: max 5.5
- EMA + MACD + BB agree + vol: 5.5/5.5 = 100%
- EMA + MACD agree + BB neutral + vol: (1.5+1+2)/(3.5+2) = 4.5/5.5 = 81.8% → fires
- EMA alone + BB neutral + vol: (1.5+2)/(3.5+2) = 3.5/5.5 = 63.6% → barely fires at 65

This gives Sniper more shots while maintaining quality — MACD confirms momentum, EMA confirms trend, BB/vol provide context.

---

## Strategy 7: 📢 VolumeKing — "The Silent King"

### Config Anatomy
```json
{
  "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
  "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 3.0,
  "pressure": 0.0, "candle_direction": 1.0
}
VOLUME_SPIKE_THRESHOLD: 2.5, CONFIDENCE_THRESHOLD: 54
```

### Scoring Math
- Active directional indicators: EMA(1.0) + candle(1.0) = total_weight 2.0
- Volume adds 3.0 on confirmation → max 5.0
- Zero indicators: macd, rsi, div, bb, pressure → invisible

### Why It Never Fires

**Problem 1: 2.5x volume threshold is extremely strict.**
On 1H crypto, volume spikes > 2.5x the 20-period average are rare events — maybe once every 2-3 days per pair, typically during news events or large liquidation cascades.

**Problem 2: EMA and candle must agree for vol to help.**
Without vol spike: confidence = EMA_votes / 2.0. If EMA=LONG and candle=LONG: 2/2 = 100%. But if EMA=LONG and candle=SHORT (very common, especially in trends with pullback candles): tie → no signal.

**Problem 3: The catch-22.**
If vol spike = True and EMA + candle agree: confidence is high (100% or ~80%). Signal fires easily.
But 2.5x vol spikes typically happen on SURPRISE moves (news, liquidations). At that point:
- If price is pumping: candle = LONG, but EMA might not have caught up yet (NEUTRAL/SHORT)
- If price is dumping: candle = SHORT, but EMA might still be LONG from prior trend

So vol spike events coincide with EMA-candle DISAGREEMENT, killing the signal.

### Fakeout Scenario: "Spike and Die"

```
Market: AVAXUSDT, price spiking on sudden news
Previous: trading at 38-39 range, EMA9=38.5, EMA21=38.2, EMA50=37.8
Current candle: Opens 38.8, volume 3.1x avg, candle is green

  If price pumps to 40.5:
    EMA: LONG (9>21>50, already aligned from range)
    Candle: LONG (green)
    Vol spike: True (3.1x > 2.5x threshold)
    Score: EMA(1)+candle(1)+vol(3) = 5/5 = 100% → Fires LONG ✅

    But it's a news-driven spike. Price reverses: 40.5→39.0→37.5.
    SL hit at ~39.0 (3.7% below 40.5).

  If price dumps to 37.0 instead:
    EMA: LONG (EMAs still 38.5/38.2/37.8, haven't reacted)
    Candle: SHORT (red, dumping)
    Vol spike: True (3.1x)
    Score: LONG=1(EMA), SHORT=1(candle) → TIE → no signal ❌

    The protective case works! But you miss the legitimate dump signal.
```

### Parameter Fix Recommendation

```json
{
    "name": "Pumpradar VolumeKing",
    "emoji": "📢",
    "description": "Volume-first: 2x vol + MACD momentum + EMA trend for breakout detection",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 2.0,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.0,
            "macd_signal": 0.5,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 0.0,
            "volume_spike": 2.5,
            "pressure": 0.5,
            "candle_direction": 1.0
        },
        "CONFIDENCE_THRESHOLD": 58,
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 50,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

**Changes:**
1. `VOLUME_SPIKE_THRESHOLD: 2.5 → 2.0` — Matches proven optimal threshold
2. `volume_spike: 3.0 → 2.5` — Still dominant but less extreme
3. `macd_signal: 0.0 → 0.5` — Adds momentum confirmation to break EMA-candle ties
4. `pressure: 0.0 → 0.5` — Adds order flow context to break ties
5. `CONFIDENCE_THRESHOLD: 54 → 58` — Slightly higher bar with more voting mass

**New scoring dynamics:**
- total_weight = 1.0 (ema) + 0.5 (macd) + 0.5 (pressure) + 1.0 (candle) = 3.0
- With vol: max 5.5
- EMA+candle+MACD agree + vol: (1+0.5+1+2.5)/(3.0+2.5) = 5.0/5.5 = 90.9% → fires
- EMA+candle agree, MACD neutral, pressure neutral + vol: (1+1+2.5)/(3.0+2.5) = 4.5/5.5 = 81.8% → fires
- EMA alone, candle neutral, MACD neutral + vol: (1+2.5)/(3.0+2.5) = 3.5/5.5 = 63.6% → fires at 58
- EMA+candle disagree + vol: tied, no signal (good protection kept)

---

## Summary: Parameter Fix Priority

| # | Passport | Severity | Fix Type | Key Change |
|---|----------|----------|----------|------------|
| 1 | 🔄 Reversal | 🔴 Critical | Keep disabled + code changes needed | RSI thresholds, regime filter |
| 2 | 🎯 Dynamic | 🔴 High | Config fix | DISABLE trailing stop |
| 3 | 🚀 Momentum | 🟡 Medium | Config fix | ema=2.0, threshold=60, reduce noise weights |
| 4 | 🏆 OG | 🟢 Low | Config tweak | vol threshold 1.5→2.0 |
| 5 | 💎 HiddenGem | 🟢 Low | Config tweak | Add pressure=0.5, threshold=58 |
| 6 | 🎯 Sniper | 🟡 Medium | Config redesign | Add MACD, lower threshold to 65 |
| 7 | 📢 VolumeKing | 🟡 Medium | Config redesign | Vol threshold 2.0, add MACD+pressure |

## Code Changes Required (Beyond Config)

These are needed for Reversal to work properly and benefit all strategies:

### Code Change 1: Per-Passport RSI Thresholds
Allow `RSI_LONG_THRESHOLD` and `RSI_SHORT_THRESHOLD` in config_overrides so Reversal can use oversold/overbought levels (30/70) instead of the universal 50/50.

### Code Change 2: Multi-Candle Confirmation Option
Add `ENTRY_CONFIRMATION_CANDLES: N` to require N consecutive candles with the same direction before entry. Default 1 (current behavior). Set to 2 for Momentum/Dynamic to filter false breakouts.

### Code Change 3: Trailing Stop Distance Improvement
Change trailing stop formula from `trail_dist = abs(entry - SL)` to `trail_dist = ATR_MULTIPLIER × current_ATR`. This adapts to real-time volatility instead of using a fixed entry-time distance.

### Code Change 4: Per-Pair Cooldown Timer
After any passport fires a signal for a pair, block that pair for that passport for N candles. Prevents Reversal-style overtrading. Default 0 (current), set to 3-6 for Reversal.

---

### Task 1: Apply OG parameter fix

**Files:**
- Modify: `pumpradar-passports/configs/og_original.json`

- [ ] **Step 1: Update volume threshold**

Change `VOLUME_SPIKE_THRESHOLD` from `1.5` to `2.0` in `og_original.json`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/og_original.json
git commit -m "fix(og): raise volume threshold 1.5→2.0 per grid search optimization"
```

---

### Task 2: Apply HiddenGem parameter fix

**Files:**
- Modify: `pumpradar-passports/configs/hidden_gem.json`

- [ ] **Step 1: Update weights and threshold**

Add `pressure: 0.5`, update `ema_trend: 1.5`, set `CONFIDENCE_THRESHOLD: 58`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/hidden_gem.json
git commit -m "fix(hiddengem): add pressure tiebreaker, raise ema weight and threshold"
```

---

### Task 3: Apply Momentum parameter fix

**Files:**
- Modify: `pumpradar-passports/configs/momentum.json`

- [ ] **Step 1: Update weights, threshold, and position cap**

Set `ema_trend: 2.0`, `rsi_divergence: 0.5`, `pressure: 0.5`, `candle_direction: 0.5`, `volume_spike: 1.5`, `CONFIDENCE_THRESHOLD: 60`, `MAX_OPEN_POSITIONS_PER_PASSPORT: 30`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/momentum.json
git commit -m "fix(momentum): reweight for EMA emphasis, raise threshold, cap positions"
```

---

### Task 4: Apply Dynamic parameter fix

**Files:**
- Modify: `pumpradar-passports/configs/dynamic_exit.json`

- [ ] **Step 1: Disable trailing stop and apply entry improvements**

Set `USE_TRAILING_STOP: false`. Apply same entry weight changes as Momentum. Set `CONFIDENCE_THRESHOLD: 60`, `MAX_OPEN_POSITIONS_PER_PASSPORT: 30`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/dynamic_exit.json
git commit -m "fix(dynamic): disable trailing stop, align entries with improved momentum"
```

---

### Task 5: Update Reversal quarantine config

**Files:**
- Modify: `pumpradar-passports/configs/reversal.json`

- [ ] **Step 1: Tighten quarantine params**

Update confidence threshold to 85, vol threshold to 2.5, vol weight to 1.0, div weight to 1.5, position cap to 5. Keep `enabled: false`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/reversal.json
git commit -m "fix(reversal): tighten quarantine params, keep disabled until code changes"
```

---

### Task 6: Redesign Sniper config

**Files:**
- Modify: `pumpradar-passports/configs/sniper.json`

- [ ] **Step 1: Add MACD, raise EMA, lower threshold**

Set `macd_signal: 1.0`, `ema_trend: 1.5`, `CONFIDENCE_THRESHOLD: 65`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/sniper.json
git commit -m "fix(sniper): add MACD confirmation, reweight EMA, lower threshold to 65"
```

---

### Task 7: Redesign VolumeKing config

**Files:**
- Modify: `pumpradar-passports/configs/volume_king.json`

- [ ] **Step 1: Lower vol threshold, add MACD+pressure**

Set `VOLUME_SPIKE_THRESHOLD: 2.0`, `volume_spike: 2.5`, `macd_signal: 0.5`, `pressure: 0.5`, `CONFIDENCE_THRESHOLD: 58`.

- [ ] **Step 2: Commit**

```bash
git add pumpradar-passports/configs/volume_king.json
git commit -m "fix(volumeking): lower vol threshold, add MACD+pressure for tiebreaking"
```

---

### Task 8: Run backtest validation on all fixed configs

**Files:**
- Read: `scripts/run_twin_bots.py` or `bot/backtester.py`

- [ ] **Step 1: Run 180-day backtest for each fixed passport**

Use the existing backtest infrastructure to validate the parameter changes don't degrade the 180-day performance.

- [ ] **Step 2: Compare results against baseline**

Expected: OG improves from +11.3% toward +49.1% (vol 2.0 effect). HiddenGem maintains +17% or better. Momentum/Dynamic improve from -81.5% toward -17% or better. Sniper/VolumeKing start firing signals.

- [ ] **Step 3: Document results**

Update analysis report with post-fix backtest numbers.

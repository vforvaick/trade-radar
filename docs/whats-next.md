# Cryptopass — What's Next

> Updated: 2026-04-07 (Session 8 — Systematic Calc Audit complete)
> Branch: `master` (`b790192`) — 289/289 tests passing, VPS deployed

---

## 🟢 Right Now (In Progress)

### Phase 4 — Research Pipeline End-to-End
Running on VPS fight-tres (Binance blocked locally):
```bash
# VPS: nohup .venv/bin/python run_research.py --all --max-per-family 3 --days 180 --pairs 10
# Log: /home/vforvaick/pumpradar-bot/logs/research_phase4_20260407.log
# Monitor:
ssh fight-tres "tail -f /home/vforvaick/pumpradar-bot/logs/research_phase4_20260407.log"
```

**What to look for when it completes:**
- Did any new candidates pass all 4 stages?
- Which strategies succeeded in which regimes?
- Check `research_experiments.db` for full results: `sqlite3 research_experiments.db "SELECT name,status,return_pct FROM experiments ORDER BY return_pct DESC LIMIT 20"`
- Update `docs/FINDINGS.md` §9 with results
- Promote winners to `passports/cryptopass-research/` if return > +10%, PF > 1.2

---

## 🔴 Immediate Priorities

### 1. Market Condition Coverage Gap — Downtrend Strategy
We have confirmed strategies for 2 of 3 BTC regimes:
- ✅ **Uptrend** → HiddenGem (+25.9%), Sniper (+26.0%), VolumeKing (+9.1%)
- ✅ **Sideways** → BBMeanRev (+7.7%), MACDDivergence (+9.1%) — now with Uptrend:1.0 fix
- ❌ **Downtrend** → **No confirmed strategy.** Existing passports show negative returns in bear markets.

**Options to explore:**
- Short-bias passport with `rsi_position` reversed (SHORT when RSI > 50 in Downtrend)
- Passive: Current passports short with same logic — check which has highest short WR in bear regime
- Research pipeline Stage 2 output will show regime-specific performance — look for downtrend survivors

### 2. ATR-Based Trailing Stop Fix
`USE_TRAILING_STOP` is permanently disabled because the current formula destroys performance (-81pp).
The fix is well-understood but not implemented:
```python
# Current (broken): trail_dist = abs(entry - original_SL)  # fixed distance, too tight
# Fix: trail_dist = ATR(14) × multiplier (e.g. 2.5)
```
**Impact:** Would unlock dynamic exits that adapt to volatility. High value for momentum passports.
**Effort:** 1 session. Requires ATR calculation + position_manager.py update + backtest validation.

### 3. RSI Thresholds Per-Passport Validation
`RSI_LONG_THRESHOLD` and `RSI_SHORT_THRESHOLD` are now per-passport overridable (Session 7 fix).
ReversalV2 uses RSI < 30 / > 70. But both ReversalV2 v0.1 (-11.78%) and v0.2 (-16.44%) are negative.
**Root cause suspected:** RSI extremes at 1H are too rare AND price often continues in the extreme direction.
**Next experiment:** Try RSI < 40 / > 60 as softer thresholds + require BB confirmation as HARD pre-filter
(not weight-based, but signal-gated: only fire if price is outside BB band).

---

## 🟡 30-Day Paper Trade Countdown
Started: 2026-04-07. Target end: 2026-05-07.

**PromotionPolicy 7-gate threshold** (need ALL to promote):
- PF ≥ 1.2
- WR ≥ 40%
- MaxDD < 15%
- ≥ 30 trades in live
- ≥ 30 days live
- Return > 0%
- No bug flags

**Top candidates to watch:**
| Passport | 90d Backtest | Edge | Watch for |
|---|---|---|---|
| MACDDivergence | +9.1% PF=1.39 | MACD+RSI divergence | Consistent 40%+ WR |
| BBMeanRev | +7.7% PF=1.32 | BB mean reversion | Needs sideways market |
| HiddenGem | +25.9% (180d) | EMA+BB+Vol selective | Needs BTC uptrend |
| Sniper | +26.0% (180d) | BB+Vol+Candle | High threshold (70%+) |

**Weekly check commands:**
```bash
ssh fight-tres "sqlite3 /home/vforvaick/pumpradar-bot/state.db \
  \"SELECT p.name, COUNT(t.id) trades, ROUND(SUM(t.pnl),2) pnl, \
  ROUND(AVG(CASE WHEN t.pnl>0 THEN 1.0 ELSE 0 END)*100,1) wr \
  FROM trade_log t JOIN passports p ON t.passport_id=p.id \
  WHERE t.closed_at > datetime('now','-7 days') \
  GROUP BY p.name ORDER BY pnl DESC\""
```

---

## 🔵 Medium-Term (Next 2-4 Sessions)

### 4. Research Engine — New Strategy Families
Phase 4 pipeline covers existing families. The 151 Trading Strategies journal has untested ideas:

| Strategy | Type | Thesis | Effort |
|---|---|---|---|
| **Funding Rate Carry** | Mean-reversion | Long when funding strongly negative (longs pay shorts → price exhaustion) | Medium — needs funding rate API |
| **OI + Liquidation Clusters** | Reversal | High OI + price at major level = liquidation magnet → reversal signal | Medium — needs OI endpoint |
| **Multi-timeframe Confluence** | Trend | 15m signal + 4H trend direction must agree | Medium — needs multi-TF data fetcher |
| **Volatility Regime Switching** | Adaptive | ATR percentile selects trend-following vs mean-reversion mode dynamically | High — requires regime detection per-scan |
| **Short-Only Passport** | Directional | Historical: short WR 65.2% vs long WR 50.0% — asymmetric edge | Low — just set direction bias weights |

**Recommended next:** Short-Only Passport (lowest effort, exploits known asymmetry).

### 5. OBV Hybrid Passport
OBV as primary signal was too noisy (28.2% WR, -11.45%). But as secondary confirmation:
```json
"bb_position": 1.5, "obv_signal": 0.5, "volume_spike": 2.0
```
Test hypothesis: OBV as a tiebreaker on top of BB+Volume combo. Target: inherit BBMeanRev's +7.7% baseline and add OBV filter to improve WR above 50%.

### 6. Donchian Re-test in Trending Market
Donchian Breakout: +0.56% PF=1.016 in Jan-Apr 2026 (choppy period). The thesis is sound but the entry conditions are wrong for ranging markets. Re-test:
- With 180d window covering a sustained trend
- Raise `donchian_signal` weight to 4.0
- Add `bb_position=1.0` as breakout confirmation filter

---

## ⚪ Long-Term (Future Sessions)

### 7. Promote First Strategy to Production
Once any passport completes 30d paper trade above all 7 PromotionPolicy gates, promote with real capital. Recommended flow:
```
Live paper → PromotionPolicy check → deploy to VPS prod namespace → start with $100 real
```
The `bot/health/promotion.py` and `bot/risk/namespace.py` already implement this — just needs a human sign-off.

### 8. Grafana Dashboard — Equity Curves
Currently tracking equity per passport in state.db but no visual. Add equity curve panel:
```bash
# fight-uno
docker compose -f docker-compose.observability.yml restart prometheus
# Then import ops/grafana-cryptopass-dashboard.json
```

### 9. Cross-Passport Portfolio Risk Limit
Currently each passport is isolated with `MAX_OPEN_POSITIONS_PER_PASSPORT`. But all 21 passports share the same pairs — during high-confluence moments they ALL fire on the same symbol simultaneously.
**Risk:** 21 passports × 3% risk = 63% equity exposed to one bad ETHUSDT move.
**Fix needed:** `bot/risk/portfolio_risk.py` should add a global cap: max 3 passports can hold the same symbol simultaneously.

### 10. Multi-Timeframe Confluence (When Ready)
Current architecture: scanner fetches 1H klines only. Multi-TF would require:
- `data_fetcher.fetch_klines(symbol, interval='4h')` call per scan
- 4H trend stored in scan context
- Confidence multiplied by 4H alignment factor
**Estimated effort:** 2-3 sessions. High impact for reducing whipsaws.

---

## 🔧 Known Technical Debt

| Issue | File | Severity | Notes |
|---|---|---|---|
| `USE_TRAILING_STOP` formula broken | `bot/position_manager.py` | HIGH | ATR-based fix designed, not implemented |
| ReversalV2 negative returns | `passports/cryptopass-research/reversal_v2.json` | MEDIUM | Needs hard EMA pre-filter in signal logic |
| Dynamic v0.2 = Momentum v0.2 metrics | `bot/backtester.py` | LOW | ATR exits may not differentiate in test window |
| `BreakoutVol` VPS equity $455 | VPS state | INFO | Paper trading live, watching |
| Binance blocked locally (MacBook) | Network | INFO | All Binance API calls must run on VPS |
| Research pipeline note: Binance blocked locally | `run_research.py` | INFO | Run on VPS: `ssh fight-tres` |

---

## 📊 Baseline Metrics to Beat

Any new strategy must beat these to be worth deploying:

| Passport | Period | Return | PF | WR | MaxDD |
|---|---|---|---|---|---|
| HiddenGem v0.1 | 180d | +25.9% | — | ~48% | — |
| Sniper v0.1 | 180d | +26.0% | — | ~48% | — |
| MACDDivergence v0.1 | 90d quality-pair | +9.1% | 1.39 | 41.5% | — |
| BBMeanRev v0.1 | 90d quality-pair | +7.7% | 1.32 | 47.3% | — |
| VolumeKing v0.1 | 180d | +9.1% | — | ~32% | — |

**Minimum bar for new passport:** return > +7%, PF > 1.2, WR > 35%, MaxDD < 20% on 90d quality pairs.

---

## 🗓️ Session Log

| Session | Date | What Was Done |
|---|---|---|
| 1-4 | 2026-03-31 → 04-04 | Initial passport design, v0.1→v0.2 optimization |
| 5 | 2026-04-05 | New strategy families (DualMA, Donchian, OBV), research engine built |
| 6 | 2026-04-05 | Research pipeline Stages 1-4, regime walk-forward fix |
| 7 | 2026-04-06 | Cryptopass overhaul: 22 passports, $500 fresh start, BTC Uptrend bug fix |
| 8 | 2026-04-07 | **Systematic calc audit: 12 bugs fixed, per-passport BTC weights, 49 new tests, VPS deployed** |

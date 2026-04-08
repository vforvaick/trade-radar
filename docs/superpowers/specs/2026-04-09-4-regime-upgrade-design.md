# 4-Regime Upgrade — Design Spec

> **For agentic workers:** This is a design specification. Use superpowers:writing-plans to create the implementation plan from this spec.

**Goal:** Replace the 3-regime EMA-based BTC trend detector with a 4-regime ADX+volatility classifier, add comprehensive regime data collection (per-scan, per-signal, per-trade), and send daily Telegram regime digest.

**Architecture:** Layered — new `RegimeDetector` (cached, multi-TF detection) + `RegimeLogger` (SQLite data collection + Telegram digest). Scanner orchestrates both. Passive mode only (log + tag, no auto-enable/disable).

**Breaking change:** All passport JSONs must migrate `BTC_TREND_WEIGHTS` from 3 keys (Uptrend/Downtrend/Sideways) to 4 keys (TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION).

---

## 1. RegimeDetector Module

**File:** `bot/regime_detector.py` (new)

### Class: RegimeDetector

```python
class RegimeDetector:
    """Cached, multi-timeframe regime detector for production use.
    
    Primary: BTC 4H candles → classify_regime() (30d return + ADX + realized vol)
    Confirmation: BTC 1H candles → EMA 9/21 crossover
    
    1H confirmation only DOWNGRADES, never upgrades:
    - 4H TREND_UP + 1H EMA9 < EMA21 → downgrade to HIGH_VOL_CHOP
    - 4H TREND_DOWN + 1H EMA9 > EMA21 → downgrade to HIGH_VOL_CHOP
    - All other cases: 4H regime stands
    """
    
    CACHE_TTL = 3600  # 1 hour, aligned with scan cycle
    
    def __init__(self):
        self._cache_regime: Optional[RegimeType] = None
        self._cache_metadata: Optional[dict] = None
        self._cache_time: float = 0
    
    def get_current_regime(self) -> RegimeType:
        """Return current market regime, cached for CACHE_TTL seconds.
        
        Steps:
        1. Check cache — if < CACHE_TTL old, return cached
        2. Fetch BTC 4H candles → classify_regime() → primary_regime  
        3. Fetch BTC 1H candles → EMA 9/21 check
        4. Apply confirmation logic (downgrades only)
        5. Cache result, return RegimeType
        
        On API failure: return last cached regime, or HIGH_VOL_CHOP as safe default.
        """
        ...
    
    def get_regime_metadata(self) -> dict:
        """Return raw data behind the regime decision.
        
        Returns:
            {
                "regime": RegimeType,
                "btc_price": float,
                "adx": float,
                "ret_30d": float,
                "realized_vol": float,
                "ema9_1h": float,
                "ema21_1h": float,
                "confirmation_matched": bool,
                "timestamp": str (ISO 8601)
            }
        """
        ...
    
    def invalidate_cache(self):
        """Force re-fetch on next call. Used in tests."""
        self._cache_time = 0
```

### Confirmation Logic

The 1H timeframe serves as a "reality check" on the 4H regime:

| 4H Primary | 1H EMA9 vs EMA21 | Final Regime | Rationale |
|---|---|---|---|
| TREND_UP | EMA9 > EMA21 | TREND_UP ✅ | Both agree, confirmed uptrend |
| TREND_UP | EMA9 < EMA21 | HIGH_VOL_CHOP ⬇️ | 4H says up but 1H pulling back — choppy |
| TREND_DOWN | EMA9 < EMA21 | TREND_DOWN ✅ | Both agree, confirmed downtrend |
| TREND_DOWN | EMA9 > EMA21 | HIGH_VOL_CHOP ⬇️ | 4H says down but 1H bouncing — choppy |
| HIGH_VOL_CHOP | any | HIGH_VOL_CHOP | Already choppy, no upgrade possible |
| LOW_VOL_COMPRESSION | any | LOW_VOL_COMPRESSION | Quiet market, 1H noise irrelevant |

**Key rule:** 1H can only downgrade trending regimes to HIGH_VOL_CHOP. It never upgrades.

### Error Handling

- Binance API timeout → return last cached regime
- No cache available + API failure → return `RegimeType.HIGH_VOL_CHOP` (safest default — triggers no penalties)
- Log warnings on every API failure

### Dependencies

- `bot.research.regime.classify_regime()` — reuse existing ADX+return+vol logic
- `bot.data_fetcher.fetch_klines()` — for BTC 4H and 1H data
- `bot.indicators.calc_ema()` — for 1H confirmation

---

## 2. BTC_TREND_WEIGHTS Migration

### bot/config.py — Default Weights

```python
# OLD (3 regimes) — REMOVE
BTC_TREND_WEIGHTS = {
    "Sideways": 1.0,
    "Downtrend": 1.0,
    "Uptrend": 0.8,
}

# NEW (4 regimes) — REPLACE
BTC_TREND_WEIGHTS = {
    "TREND_UP": 0.8,              # selective in bull — only high-conviction passes
    "TREND_DOWN": 1.0,            # trade freely in bear (75% short WR historically)
    "HIGH_VOL_CHOP": 0.9,         # slight penalty — choppy = lower quality signals
    "LOW_VOL_COMPRESSION": 1.0,   # quiet market, trade freely
}
```

### Passport JSON Migration

All 22 enabled passports must update their `BTC_TREND_WEIGHTS` override (if present):

**Mean-reversion passports** (BBMeanRev, RSIContrarian, MACDDivergence, ReversalV2, Reversal):
```json
"BTC_TREND_WEIGHTS": {
    "TREND_UP": 1.0,
    "TREND_DOWN": 1.0,
    "HIGH_VOL_CHOP": 1.0,
    "LOW_VOL_COMPRESSION": 1.0
}
```
Rationale: mean-reversion strategies profit in all BTC conditions, no penalty needed.

**Trend-following passports** (HiddenGem, Sniper, VolumeKing, Momentum, Dynamic, OG, etc):
Use default weights (no override needed) OR explicit:
```json
"BTC_TREND_WEIGHTS": {
    "TREND_UP": 0.8,
    "TREND_DOWN": 1.0,
    "HIGH_VOL_CHOP": 0.9,
    "LOW_VOL_COMPRESSION": 1.0
}
```

**Passports without BTC_TREND_WEIGHTS override:**
Will use the new defaults from config.py automatically. No migration needed.

### scorer.py — No Code Change Needed

```python
# Line 126 — same logic, new key names flow through automatically
btc_weight = config.BTC_TREND_WEIGHTS.get(btc_trend, 1.0)
```

The `btc_trend` parameter will now receive `"TREND_UP"` instead of `"Uptrend"`, which matches the new config keys.

### Backward Compatibility Warning

Add to `PassportRunner._load_passports()`:
```python
old_keys = {"Uptrend", "Downtrend", "Sideways"}
if passport.config_overrides.get("BTC_TREND_WEIGHTS"):
    keys = set(passport.config_overrides["BTC_TREND_WEIGHTS"].keys())
    if keys & old_keys:
        logger.warning(
            "Passport %s has old 3-regime BTC_TREND_WEIGHTS keys %s — "
            "migrate to 4-regime keys (TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION)",
            passport.name, keys & old_keys
        )
```

---

## 3. RegimeLogger Module

**File:** `bot/regime_logger.py` (new)

### SQLite Schema

Three new tables in `state.db`:

```sql
-- Per-scan regime snapshot (1 row per hourly scan)
CREATE TABLE IF NOT EXISTS regime_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    regime TEXT NOT NULL,
    btc_price REAL,
    adx REAL,
    ret_30d REAL,
    realized_vol REAL,
    ema9_1h REAL,
    ema21_1h REAL,
    confirmation_matched INTEGER,
    total_signals INTEGER,
    total_positions_opened INTEGER
);

-- Per-signal regime tag (1 row per signal generated, BEFORE any filtering)
CREATE TABLE IF NOT EXISTS signal_regime_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    regime TEXT NOT NULL,
    passport_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence_raw REAL,
    confidence_adjusted REAL,
    btc_weight_applied REAL,
    was_executed INTEGER DEFAULT 0,
    skip_reason TEXT
);

-- Extend existing trade_log with regime columns
-- (ALTER TABLE, not CREATE — table already exists)
ALTER TABLE trade_log ADD COLUMN regime_at_open TEXT;
ALTER TABLE trade_log ADD COLUMN regime_at_close TEXT;
```

### Class: RegimeLogger

```python
class RegimeLogger:
    """Handles all regime data collection and reporting."""
    
    def __init__(self, state_store: StateStore):
        self.state_store = state_store
        self._ensure_tables()
    
    def log_scan(self, regime: RegimeType, metadata: dict, 
                 total_signals: int, total_opened: int):
        """Log per-scan regime snapshot."""
        ...
    
    def log_signal(self, regime: str, passport_name: str, symbol: str,
                   direction: str, confidence_raw: float, confidence_adjusted: float,
                   btc_weight: float, was_executed: bool, skip_reason: Optional[str] = None):
        """Log per-signal regime tag."""
        ...
    
    def tag_trade_open(self, trade_id: int, regime: str):
        """Tag a newly opened trade with current regime."""
        ...
    
    def tag_trade_close(self, trade_id: int, regime: str):
        """Tag a closing trade with current regime."""
        ...
    
    def generate_daily_digest(self) -> str:
        """Generate daily regime report text for Telegram.
        
        Content:
        - Current regime + BTC price + ADX + 30d return
        - Regime distribution over last 24h (% of scans per regime)
        - Per-passport PnL by regime
        - Insight: how many trades opened in "wrong" regime
        """
        ...
    
    def send_daily_digest(self, telegram_bot):
        """Send daily digest to Telegram log topic."""
        text = self.generate_daily_digest()
        telegram_bot.send_log(text)
```

### Telegram Daily Digest Format

```
📊 Cryptopass Daily Regime Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 Current: HIGH_VOL_CHOP
📈 BTC: $87,234 | ADX: 18.3 | 30d: +3.2% | Vol: 42.1%

⏰ Regime Distribution (24h):
  TREND_UP:            8/24 scans (33%)
  HIGH_VOL_CHOP:      12/24 scans (50%)
  LOW_VOL_COMPRESSION: 4/24 scans (17%)

📊 Top 5 Passports by Regime PnL:
  🏆 HiddenGem:     +$12.30 (8 trades, all in TREND_UP)
  ✅ BBMeanRev:     +$5.10 (4 trades, mixed regimes)
  📉 BreakoutVol:   -$5.20 (3 trades in HIGH_VOL_CHOP)

⚠️ 6 passports opened trades in potentially wrong regime
💡 Signals: 164 generated → 25 executed (15% execution rate)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Digest Timing

- Trigger: check in `PassportRunner` main loop if UTC midnight crossed since last digest
- Store `last_digest_date` in `session_state` table to prevent duplicates
- On VPS restart: don't re-send if already sent today

---

## 4. Integration Points

### 4.1 Scanner Changes

**File:** `bot/scanner.py`

```python
class Scanner:
    def __init__(self, interval="1h", limit=100):
        # ... existing init ...
        self.regime_detector = RegimeDetector()
        # self.btc_trend stays as string field for backward compat
    
    def update_btc_trend(self):
        """Update BTC regime (replaces old EMA-only detection)."""
        try:
            regime = self.regime_detector.get_current_regime()
            self.btc_trend = regime.value  # "TREND_UP", "TREND_DOWN", etc.
            metadata = self.regime_detector.get_regime_metadata()
            print(f"[Scanner] BTC Regime: {self.btc_trend} (ADX: {metadata.get('adx', '?'):.1f})")
        except Exception as e:
            logger.exception("Failed to update regime")
            self.btc_trend = "HIGH_VOL_CHOP"  # safe default
```

### 4.2 PassportRunner Changes

**File:** `bot/passport_runner.py`

```python
class PassportRunner:
    def __init__(self, ...):
        # ... existing init ...
        self.regime_logger = RegimeLogger(self.state_store)
        self._last_digest_date = None
    
    def run_scan_cycle(self):
        # ... existing scan logic ...
        
        # After all passports scanned:
        self.regime_logger.log_scan(
            regime=RegimeType(self.scanner.btc_trend),
            metadata=self.scanner.regime_detector.get_regime_metadata(),
            total_signals=total_signals,
            total_opened=total_opened
        )
        
        # Daily digest check
        self._check_daily_digest()
    
    def _process_signal(self, passport, signal):
        # ... existing signal processing ...
        
        # Log signal with regime tag (before position open/skip decision)
        self.regime_logger.log_signal(
            regime=self.scanner.btc_trend,
            passport_name=passport.name,
            symbol=signal.symbol,
            direction=signal.direction,
            confidence_raw=signal.confidence_raw,
            confidence_adjusted=signal.confidence,
            btc_weight=signal.btc_weight,
            was_executed=opened,
            skip_reason=skip_reason
        )
    
    def _check_daily_digest(self):
        today = datetime.utcnow().date()
        if self._last_digest_date != today and datetime.utcnow().hour == 0:
            self.regime_logger.send_daily_digest(self.telegram_bot)
            self._last_digest_date = today
```

### 4.3 Trade Tagging

When a position opens:
```python
# In position_manager or passport_runner
self.regime_logger.tag_trade_open(trade_id, current_regime)
```

When a position closes (TP/SL hit):
```python
self.regime_logger.tag_trade_close(trade_id, current_regime)
```

### 4.4 Backtester Changes

**File:** `bot/backtester.py`

The backtester already uses `determine_btc_trend_at()` to get BTC trend per candle. This function currently returns "Uptrend"/"Downtrend"/"Sideways".

Change `determine_btc_trend_at()` to use `classify_regime()` instead of EMA crossover:
```python
def determine_btc_trend_at(btc_df, timestamp):
    """Determine regime at a specific timestamp using 4-regime classifier."""
    # Slice btc_df up to timestamp
    # Call classify_regime(btc_slice) → RegimeType
    # Return regime.value string
```

This ensures backtester and live system use identical regime logic.

---

## 5. Passport JSON Schema Extension

### New Optional Field: `active_regimes`

```json
{
    "name": "HiddenGem",
    "version": "0.4",
    "active_regimes": null,
    "config_overrides": {
        "BTC_TREND_WEIGHTS": {
            "TREND_UP": 0.8,
            "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 0.9,
            "LOW_VOL_COMPRESSION": 1.0
        }
    }
}
```

- `active_regimes: null` → passport runs in all regimes (current behavior, passive mode)
- `active_regimes: ["TREND_UP", "LOW_VOL_COMPRESSION"]` → passport only runs in these regimes (future Phase 2)

**Phase 1 (this spec):** Field is parsed but ignored. PassportRunner logs if a passport would have been skipped under active filtering.
**Phase 2 (future):** PassportRunner enforces `active_regimes` filtering.

---

## 6. Testing Strategy

### Unit Tests

| Test | File | What |
|---|---|---|
| `test_regime_detector_cache` | `tests/test_regime_detector.py` | Cache TTL works, doesn't re-fetch within 1H |
| `test_regime_detector_confirmation` | same | 1H downgrade logic for all 6 combinations |
| `test_regime_detector_api_failure` | same | Returns safe default on timeout |
| `test_regime_logger_log_scan` | `tests/test_regime_logger.py` | SQLite insert correct |
| `test_regime_logger_log_signal` | same | Per-signal tagging works |
| `test_regime_logger_daily_digest` | same | Digest text format correct |
| `test_btc_weights_migration` | `tests/test_regime_migration.py` | New 4-key format accepted |
| `test_btc_weights_old_format_warning` | same | Old 3-key format logged as warning |
| `test_backtester_regime_parity` | same | Backtester uses same classify_regime() as live |

### Integration Tests

| Test | What |
|---|---|
| `test_scanner_uses_regime_detector` | Scanner.update_btc_trend() returns 4-regime value |
| `test_passport_runner_logs_regime` | Full scan cycle produces regime_snapshots row |
| `test_signal_tagged_with_regime` | Generated signal has regime in signal_regime_log |

---

## 7. Migration Checklist

1. Create `bot/regime_detector.py`
2. Create `bot/regime_logger.py`
3. Update `bot/config.py` — BTC_TREND_WEIGHTS 3→4 keys
4. Update `bot/scanner.py` — use RegimeDetector
5. Update `bot/passport_runner.py` — add RegimeLogger
6. Update `bot/backtester.py` — determine_btc_trend_at() uses classify_regime()
7. Migrate all 22 passport JSONs — BTC_TREND_WEIGHTS keys
8. Add backward compat warning for old 3-key format
9. Create tests (9 unit + 3 integration)
10. Run full test suite (296 + ~12 new = ~308 tests)
11. Update `docs/FINDINGS.md` with regime upgrade notes
12. Update `passports/VERSIONS.md` with version bumps
13. Deploy to VPS

---

## 8. Risk Assessment

| Risk | Mitigation |
|---|---|
| 4H API call adds latency | Cache TTL = 1H, one call per scan cycle max |
| classify_regime() needs 45+ bars | Fetch 200 bars of BTC 4H (safe margin) |
| Regime flipping too fast | 1H confirmation prevents false trending, 4H primary is stable |
| Passport migration breaks live | Backward compat warning + all-or-nothing commit |
| SQLite write overhead | 3 tables, ~25 rows per scan cycle, negligible |
| Telegram rate limit | Daily digest = 1 message/day, well within limits |

---

## 9. Future Phase 2 (Not in This Spec)

- **Active regime filtering** — PassportRunner reads `active_regimes` and skips non-matching passports
- **Regime-based position sizing** — Reduce risk in HIGH_VOL_CHOP (2% instead of 3%)
- **Regime transition alerts** — Telegram alert on regime change (not just daily)
- **Regime performance dashboard** — Grafana panel showing PnL by regime over time

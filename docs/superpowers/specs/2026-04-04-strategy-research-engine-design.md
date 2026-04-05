# Strategy Research Engine — Design Specification

**Date:** 2026-04-04
**Status:** Approved (pending final review)
**Branch:** `feature/strategy-research-engine-v1`

---

## 1. Problem Statement

The current Pumpradar system runs 7 hand-crafted passport strategies via a scoring engine. 180-day backtesting revealed that:

- Only 3 of 7 passports were profitable (HiddenGem +25.9%, Sniper +26.0%, VolumeKing +9.1%)
- The profitable strategies share a common trait: **fewer active indicators = higher selectivity = better results**
- Manual parameter tuning (v0.2) caused 5/6 regressions, proving that intuition-based optimization is dangerous
- The system lacks regime awareness, walk-forward validation, and portfolio-level risk management

**Goal:** Build a systematic Strategy Research Engine that generates hundreds of passport candidates from 23 strategy families, validates them through a rigorous 4-stage pipeline, and deploys the 10-20 best orthogonal strategies as a portfolio.

**Success criteria:**
- Portfolio Sharpe > 0.7 across regimes (TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION)
- Maximum portfolio drawdown < 30%
- Each selected strategy passes walk-forward OOS validation + parameter perturbation
- Full audit trail from generation through retirement

---

## 2. Strategy Family Taxonomy (23 Families + 3 Modules)

### Scoring-Based Families (1-18)

These use the existing `scorer.py` weighted-indicator model. Each family is a specific combination of indicator weights and thresholds.

| # | Family | Core Indicators | Regime Fit |
|---|--------|----------------|------------|
| 1 | EMA Crossover | EMA fast/slow crossover | Trending |
| 2 | RSI Momentum | RSI with dynamic thresholds | All |
| 3 | Bollinger Breakout | BB squeeze → breakout | Low-vol → expansion |
| 4 | MACD Divergence | MACD histogram + signal cross | Trending |
| 5 | Volume Spike Breakout | Volume anomaly + direction confirm | Event-driven |
| 6 | Stochastic Reversal | StochRSI oversold/overbought | Ranging |
| 7 | OBV Trend | On-Balance Volume trend confirmation | Trending |
| 8 | Ichimoku Cloud | Cloud position + TK cross | Trending |
| 9 | VWAP Deviation | Price vs VWAP ± σ | Intraday mean-reversion |
| 10 | Keltner Channel | ATR-based channel breakout | Volatility expansion |
| 11 | Donchian Breakout | N-period high/low breakout | Trending/breakout |
| 12 | Heikin-Ashi Momentum | HA candle color persistence | Trending |
| 13 | Williams %R | Extreme zone reversals | Ranging |
| 14 | CCI Divergence | CCI + price divergence | All |
| 15 | Money Flow Index | Volume-weighted RSI variant | All |
| 16 | Hull MA Crossover | HMA fast response crossover | Trending |
| 17 | Supertrend | ATR-based trend following | Trending |
| 18 | Pivot Point Bounce | S/R from pivot calculations | Ranging/intraday |

### Custom Logic Families (19-23)

These require code beyond weighted scoring — state machines, multi-bar patterns, or external data.

| # | Family | Logic Type | Data Requirements |
|---|--------|-----------|-------------------|
| 19 | Funding Rate Carry | Long/short based on funding rate extremes | funding_rate (8h) |
| 20 | Open Interest Divergence | OI vs price divergence = positioning signal | open_interest |
| 21 | Liquidation Cascade | Detect liquidation cluster → fade or ride | liquidation_data |
| 22 | Auction / Volume Structure | Volume profile + POC / VAH / VAL levels | tick_volume or 15m |
| 23 | Regime Adaptive / Volatility Regime Switching | Switch sub-strategy based on current regime | multi-TF, ATR, ADX |

### Modules (composable, not families)

| Module | Type | Usage |
|--------|------|-------|
| ADX Filter | Entry filter | Gate: only enter when ADX > threshold |
| Parabolic SAR | Exit module | Trail stop using SAR dots |
| Multi-TF Orchestrator | Template | Align signals across 15m/1H/4H |
| Regime Gate | Entry filter | Block entries in incompatible regimes |

---

## 3. System Architecture

### 3.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  UNIFIED RESEARCH FRAMEWORK                                      │
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │ Feature    │→ │ Strategy   │→ │ Order      │→ │ Portfolio  │ │
│  │ Store      │  │ Runner     │  │ Intent     │  │ Risk Mgr   │ │
│  │            │  │            │  │ Layer      │  │            │ │
│  │ • OHLCV    │  │ • on_bar() │  │            │  │ • hard     │ │
│  │   15m/1H/4H│  │ • generate │  │ • symbol   │  │   limits   │ │
│  │ • funding  │  │   _signal()│  │ • side     │  │ • soft     │ │
│  │ • OI/liq   │  │            │  │ • size_req │  │   alerts   │ │
│  │ • ATR/vol  │  │            │  │ • stop/TP  │  │ • exposure │ │
│  │ • returns  │  │            │  │ • confid.  │  │   governor │ │
│  │ • quality  │  │            │  │ • metadata │  │            │ │
│  │   flags    │  │            │  │            │  │            │ │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘ │
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │ Position   │→ │ Evaluation │→ │ Passport   │→ │ Portfolio  │ │
│  │ Manager    │  │ Pipeline   │  │ Registry   │  │ Construct  │ │
│  │            │  │            │  │            │  │            │ │
│  │ • sizing   │  │ Stage 1:   │  │ • schema v2│  │ • low corr │ │
│  │ • stop     │  │  viability │  │ • 5 core + │  │ • risk     │ │
│  │ • cooldown │  │ Stage 2:   │  │   metadata │  │   parity   │ │
│  │ • trailing │  │  regime WF │  │ • lineage  │  │ • marginal │ │
│  │ • pyramidng│  │ Stage 3:   │  │ • lifecycle│  │   contrib  │ │
│  │            │  │  param pert│  │   state    │  │ • cluster  │ │
│  │            │  │ Stage 4:   │  │ • immutable│  │   cap      │ │
│  │            │  │  orthogon. │  │   artifacts│  │            │ │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ EXPERIMENT TRACKER                                          │  │
│  │ run_id | code_version | data_version | feature_version |    │  │
│  │ regime_def_version | passport_hash | metrics |              │  │
│  │ rejected_by (primary + secondary) | tags | notes            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ OPERATIONAL HEALTH MONITOR                                  │  │
│  │ last_scan_ts | last_bar_ts | api_latency | stale_detect |  │  │
│  │ telegram_heartbeat | db_health | error_counts               │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Strategy Bases

#### ScoringStrategyBase (families 1-18)

Reuses existing `scorer.py` weighted-indicator model. Each passport specifies indicator weights and thresholds. The base class handles:

- `calc_indicators(df)` — compute all indicators on OHLCV data
- Weight → score aggregation via scorer
- NEUTRAL vote dilution behavior preserved

#### CustomLogicStrategyBase (families 19-23)

For strategies that need state machines, external data, or non-linear logic:

```python
class CustomLogicStrategyBase(ABC):
    @abstractmethod
    def prepare_context(self, feature_store: FeatureStore) -> dict:
        """Pull needed features, compute strategy-specific derived data."""

    @abstractmethod
    def generate_signal(self, context: dict) -> Signal:
        """Produce Signal(direction, conviction, metadata) or NoSignal."""

    def desired_position(self, context: dict) -> PositionIntent:
        """Optional: express target position state directly.
        Default: delegates to generate_signal → PositionManager."""

    def on_bar(self, bar: Bar, feature_store: FeatureStore) -> Signal:
        """Convenience: prepare_context + generate_signal in one call."""
        ctx = self.prepare_context(feature_store)
        return self.generate_signal(ctx)
```

**No `score()` method.** Strategies produce signals; the Position Manager and Portfolio Risk Manager handle execution.

### 3.3 Signal ↔ Position Separation

```python
@dataclass
class Signal:
    direction: Literal["long", "short", "flat"]
    conviction: float          # 0.0 - 1.0
    metadata: dict             # strategy-specific context
    timestamp: datetime
    symbol: str
    passport_id: str

@dataclass
class OrderIntent:
    signal: Signal
    requested_size_pct: float  # % of strategy allocation
    suggested_stop: float
    suggested_tp: list[float]  # TP cascade
    priority: int              # 1 (highest) to 10 (lowest); for conflict resolution when caps exceeded
    cooldown_remaining: int    # bars until next allowed entry
```

**Flow:** Strategy → Signal → Position Manager → OrderIntent → Portfolio Risk Manager → Execution

The Position Manager converts signals to order intents using execution_config (stop logic, cooldown, pyramiding rules). The Portfolio Risk Manager then approves, resizes, rejects, or queues the intent.

### 3.4 Feature Store

Replaces simple data bus with normalized, cached, quality-flagged data layer.

**Responsibilities:**
- Normalize timestamps across timeframes (15m, 1H, 4H aligned)
- Cache base features: returns, ATR, rolling volatility, OBV
- Expose data quality flags per symbol per timeframe
- Compute once per bar, consumed by all passports
- Handle missing data gracefully (interpolation rules, gap flags)

**Quality flags:**
- `missing_bars_pct`: percentage of expected bars missing
- `max_consecutive_gap`: longest gap in bars
- `stale_since`: timestamp of last fresh data
- `critical_feature_availability`: per-feature availability map

### 3.5 Family Registry

Each family declares its full compatibility and parameter space:

```python
@dataclass
class FamilyRegistration:
    name: str
    type: Literal["scoring", "custom"]
    required_data: list[str]          # ["1h", "4h", "funding_rate"]
    tunable_params: dict              # {param: {type, min, max, step, default, perturbation_rule}}
    compatible_filters: list[str]     # ["adx_filter", "regime_gate"]
    compatible_position_managers: list[str]  # ["standard", "trailing_atr"]
    compatible_regimes: list[str]     # ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION", "all"]
    incompatible_modules: list[str]   # ["parabolic_exit"] for MR strategies
    passport_generation_rules: dict   # grid bounds, constraints, exclusions
    validation_profile: str           # walk-forward template name
    min_trades_threshold: int         # family-specific (30 for intraday, 12-20 for swing)
    min_exposure_days: int            # for carry/funding families (alternative to trade count)
    max_concurrent_per_family: int    # cap for live deployment (default: 3)
```

**Parameter specification per tunable param:**

```python
{
    "ema_fast": {
        "type": "int",
        "min": 5, "max": 50, "step": 1, "default": 12,
        "perturbation_rule": "relative_15pct",
        "rounding": "int"
    },
    "use_volume_confirm": {
        "type": "bool",
        "perturbation_rule": "flip"  # toggle on/off
    }
}
```

### 3.6 Scheduler + Worker Model (Live Execution)

```
┌──────────────────┐
│   Orchestrator    │
│   / Scheduler     │
│                   │
│ • load registry   │
│ • scan cycle mgmt │
│ • dispatch jobs   │
│ • aggregate       │
│ • retry policy    │
│ • rate limiting   │
│ • timeout per     │
│   passport        │
│ • graceful degrad │
└────────┬─────────┘
         │ dispatch
    ┌────┼────┐
    ▼    ▼    ▼
  ┌───┐┌───┐┌───┐
  │W1 ││W2 ││W3 │  Passport Workers
  │   ││   ││   │  (independent state)
  └─┬─┘└─┬─┘└─┬─┘
    │    │    │
    └────┼────┘
         ▼
  ┌──────────────┐
  │ Order Intent │
  │ Aggregator   │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Portfolio    │
  │ Risk Manager │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Execution    │
  │ Engine       │
  │ (paper/prod) │
  └──────────────┘
```

---

## 4. Evaluation Pipeline (4-Stage Filter)

### Stage 1 — Minimum Viability (Sanity Gate)

Stage 1 is a **sanity gate**, not a quality gate. Its purpose is to kill obviously broken candidates cheaply before expensive validation.

Organized into 3 sub-groups:

#### A. Data Sanity
| Check | Rule |
|-------|------|
| Missing bars | < 5% total |
| Max consecutive gap | < 20 bars (default; up to 50 for long-lookback families) |
| Timestamp alignment | All timeframes properly aligned |
| Funding/OI availability | Required custom fields present above Y% |
| Warmup sufficiency | Enough bars for longest lookback + 50 buffer (e.g., EMA_50 + RSI_14 = min 100 bars) |

#### B. Trading Sanity
| Check | Rule |
|-------|------|
| Minimum trades | Family-specific: ≥30 (intraday), ≥12-20 (swing/trend), ≥ min_exposure_days (carry) |
| Leverage behavior | No pathological leverage spikes |
| Fees vs gross PnL | Transaction costs < 80% of gross PnL |
| Fill realism | No impossible fills (price outside bar range) |

#### C. Catastrophe Screen
| Check | Rule |
|-------|------|
| Max drawdown | < 50% (default); family-specific: < 40% for MR, < 60% for trend-following |
| Net return floor | > -20% |
| Outlier dependency | No single trade responsible for > 50% of total PnL |

**Kill immediately** if any check fails.

### Stage 2 — Regime-Split Walk-Forward

#### Regime Classification (Exclusive, Priority-Ordered)

Applied to BTC 4H data. Each bar belongs to exactly one regime:

1. **Trend Up**: 30d return > +10% AND ADX > 25
2. **Trend Down**: 30d return < -10% AND ADX > 25
3. **High-Vol Chop**: abs(30d return) ≤ 10% AND realized vol > median(60d rolling vol)
4. **Low-Vol Compression**: abs(30d return) ≤ 10% AND realized vol ≤ median(60d rolling vol)

Canonical regime enum: `{TREND_UP, TREND_DOWN, HIGH_VOL_CHOP, LOW_VOL_COMPRESSION}`. All code must reference this enum exclusively.

#### Walk-Forward Windows

- **Minimum data**: 240-300 days for full 3-fold validation. If only 180d available, run 1 fold and flag as `limited_validation` (not eligible for production promotion without re-validation on 240d+ data).
- **Train**: 120 days
- **Test (OOS)**: 60 days
- **Slide**: 30 days
- **Result**: 3 walk-forward folds with proper non-overlapping OOS periods

If only 180d available: run 1 fold only, flag as `limited_validation` (requires 240d+ re-validation before production).

#### Pass Criteria
- OOS positive return in **at least 2 of 3 folds**
- Median OOS return > 0 (not just count-based)
- Worst fold not catastrophic (DD < 40% in any single fold)
- No single regime shows return < -50% (regimes with < 5% of total bars: flagged `limited_regime_data`, pass if return > -30%)
- Aggregate OOS Sharpe > 0.3 OR Calmar > 0.5 OR Profit Factor > 1.1 (multi-metric OR — regime specialists with weak Sharpe but strong Calmar/PF are accepted)

### Stage 3 — Parameter Perturbation (Fragility Test)

For each surviving passport:

#### Perturbation Rules
- Per-parameter rules from Family Registry (not global ±15%):
  - `int` params: ±15%, rounded to int
  - `float` params: ±15%
  - `bool` params: flip (toggle on/off)
  - `categorical` params: cycle through alternatives
  - Bounds respected (never go below min or above max)
- **50 Monte Carlo iterations** (default; 30-50 for simple families, up to 100 for complex)

#### Survival Definition
A perturbation "survives" if:
- OOS return > 0
- DD not catastrophic (< 50% or family-specific Stage 1 threshold)
- Sharpe > 0.1 OR Profit Factor > 1.05 (lower than Stage 2 to allow for perturbation noise)

#### Pass Criteria
- **Survival rate ≥ 60%**
- Mean perturbed return within 50% of original (no cliff-edge)
- **5th percentile return floor** > -30% (distribution-aware, not single outlier rule)
- IQR of perturbed outcomes reasonable (low fragility)

### Stage 4 — Orthogonality & Portfolio Utility

Among all Stage 3 survivors:

#### Triple Overlap Measurement
1. **Daily equity correlation** — pairwise Pearson on daily returns. Threshold: < 0.4 = orthogonal, 0.4-0.6 = acceptable, > 0.6 = redundant
2. **Trade overlap** — same asset + same direction + overlapping holding period + notional > 1% of allocation. Threshold: < 20% overlap = orthogonal
3. **Drawdown coincidence** — simultaneous drawdown events (both > 10% DD within 5-day window). Threshold: < 30% coincidence = orthogonal

#### Selection Criteria
- **Family cap**: max 3 strategies per family
- **Cluster cap**: max 3 strategies per correlation cluster (hierarchical clustering, Pearson threshold 0.6)
- **Marginal contribution**: adding strategy X must improve portfolio composite utility. Composite = `(OOS_Sharpe + OOS_Calmar) / (MaxDD / 30)`. Accept only if ΔUtility > +0.05.
- **Final portfolio**: 10-20 orthogonal strategies

#### Pipeline Output

```python
@dataclass
class ExperimentResult:
    run_id: str                    # "exp-2026-04-04-001"
    code_version: str              # git SHA
    data_version: str              # "300d-2025-06-to-2026-04"
    feature_version: str           # feature store version
    regime_definition_version: str # regime classifier version
    validation_profile_id: str     # which walk-forward template

    total_generated: int           # passports created
    stage1_survivors: int          # passed viability
    stage2_survivors: int          # passed regime walk-forward
    stage3_survivors: int          # passed perturbation
    stage4_selected: int           # portfolio-worthy

    portfolio_selection_reason: dict  # why these specific strategies
    stage_metrics_summary: dict       # aggregate stats per stage

    rejected_log: list[dict]       # full audit trail
    # Each entry: {passport_hash, rejected_at_stage,
    #              primary_reason, secondary_reasons, metrics}
```

---

## 5. Versioning v2 — Coexistence Model

### Core Philosophy

**Passport = immutable artifact. Lifecycle state lives in registry.**

Once created, a passport JSON file is never edited in place. Any change creates a new version.

### Identity Model

Every passport has three distinct identifiers:

```python
passport_id: str       # "psp_01HZX..." — permanent, UUID-based, never changes
slug: str              # "ema_crossover-fast_12_26" — human-readable, mutable
passport_version: str  # "2.1" — strategy/params version (semver)
schema_version: int    # 2 — JSON format version (separate from strategy version)
```

### Lineage Tracking

```json
{
    "passport_id": "psp_abc123",
    "parent_passport_id": "psp_xyz789",
    "root_passport_id": "psp_xyz789",
    "lineage_type": "param_tweak"
}
```

**Lineage types:** `genesis | param_tweak | logic_change | rollback | clone | migration`

### Version Semantics (Hard Rules)

**Minor bump (v1.1, v1.2):** ONLY when:
- Signal logic unchanged
- Indicator set unchanged
- Execution logic unchanged
- Risk model unchanged
- Only numeric parameter/threshold/bounds changed

**Major bump (v2.0):** When ANY of these change:
- Indicator set
- Feature engineering logic
- Entry/exit logic
- Position management approach
- Regime filter logic
- Cost model assumptions
- Validation profile materially changed

**Rollback:** Always creates a new version with:
- `lineage_type: "rollback"`
- `rollback_target_version: "1.0"`
- New version number (e.g., v1.3 = v1.0 params, but new context)

### Status Lifecycle

```
draft → generated → backtested → paper_live → candidate → production
                  ↘ failed_validation                    ↘ retired → archived
```

| Status | Meaning |
|--------|---------|
| `draft` | Manual creation, not yet complete |
| `generated` | Auto-generated by research engine |
| `backtested` | Completed evaluation pipeline |
| `paper_live` | Running in paper trading |
| `candidate` | Passed paper period, eligible for promotion |
| `production` | Live trading with real exposure |
| `retired` | Removed from production, preserved for audit |
| `archived` | Historical, no longer considered for any use |
| `failed_validation` | Failed at a specific evaluation stage |

### Passport Schema v2 (5 Core Config Sections + Metadata)

5 core sections: `family`, `signal_config`, `execution_config`, `risk_config`, `validation_profile`. Plus metadata fields: `lineage`, `changelog`, identity fields (`passport_id`, `slug`, versions).

```json
{
    "passport_id": "psp_01HZX...",
    "slug": "ema_crossover-fast_12_26",
    "passport_version": "1.0",
    "schema_version": 2,

    "lineage": {
        "parent_passport_id": null,
        "root_passport_id": "psp_01HZX...",
        "lineage_type": "genesis"
    },

    "family": {
        "name": "ema_crossover",
        "type": "scoring",
        "version": "1.0"
    },

    "signal_config": {
        "indicators": {
            "ema_fast": 12,
            "ema_slow": 26,
            "rsi_period": 14
        },
        "weights": {
            "ema": 2.0,
            "rsi": 1.0,
            "macd": 0.0,
            "bb": 0.0,
            "volume": 1.5
        },
        "thresholds": {
            "confidence_threshold": 65,
            "rsi_long": 45,
            "rsi_short": 55
        }
    },

    "execution_config": {
        "entry_policy": "immediate",
        "exit_policy": "tp_cascade_70_20_10",
        "stop_logic": "fixed_sl",
        "stop_pct": 3.0,
        "cooldown_bars": 0,
        "pyramiding": false,
        "modules": ["adx_filter"]
    },

    "risk_config": {
        "risk_per_trade_pct": 3.0,
        "leverage_tiers": {
            "default": 5,
            "high_vol": 3,
            "low_vol": 7
        },
        "max_concurrent_positions": 50,
        "max_per_symbol": 1
    },

    "validation_profile": {
        "walk_forward": "120d_train_60d_test",
        "regime_template": "btc_4regime_exclusive",
        "perturbation_bounds_pct": 15,
        "min_trades": 30
    },

    "changelog": [
        {
            "timestamp": "2026-04-04T10:00:00Z",
            "change_type": "genesis",
            "fields_changed": [],
            "summary": "Initial generation from ema_crossover family",
            "author": "research_engine_v1"
        }
    ]
}
```

### Legacy Adapter

```python
class LegacyScoringAdapter:
    """Wraps existing v0.x passports (schema_version 1) into schema v2 interface."""

    def __init__(self, legacy_passport_path: str):
        self.config = load_json(legacy_passport_path)
        self.schema_version = 1
        self.origin = "legacy"
        self.canonicalized = True
        self.migrated_to_schema_v2 = False
        self.comparable_with_modern_metrics = "partial"

    def to_signal(self, scorer_result) -> Signal:
        """Convert scorer.py output to Signal dataclass."""
```

### Coexistence Rules

1. **Multiple versions of same lineage can run simultaneously** in paper trading
2. **Max 2-3 live variants per lineage** (1 control + 1-2 challengers with explicit experiment tags)
3. **Production promotion** requires: Stage 4 pass + promotion gate (see §6.4)
4. **Retirement**: status changes in registry, passport file untouched (immutable)
5. **Never delete** — all versions preserved forever for audit trail

### Storage Layout

```
pumpradar-passports/
├── registry.json              # searchable catalog (full metadata per passport)
├── legacy/                    # existing 7 passports (schema v1, immutable)
│   ├── og_original.json
│   ├── hidden_gem.json
│   ├── momentum.json
│   ├── dynamic_exit.json
│   ├── reversal.json
│   ├── sniper.json
│   └── volume_king.json
├── generated/                 # engine-produced passports (schema v2, immutable)
│   ├── ema_crossover/
│   │   ├── fast_12_26-v1.0.json
│   │   └── fast_12_26-v1.1.json
│   └── volume_breakout/
│       └── obv_heavy-v1.0.json
├── lineages/                  # per-lineage summary and version tree
│   └── ema_crossover-fast_12_26.json
├── experiments/               # backtest/research run results
│   └── exp-2026-04-04-001.json
└── runs/                      # live paper/production observation data
    └── run-2026-04-15-paper-batch1.json
```

### Registry Entry Schema

Each passport entry in `registry.json`:

```json
{
    "passport_id": "psp_01HZX...",
    "slug": "ema_crossover-fast_12_26",
    "family": "ema_crossover",
    "variant": "fast_12_26",
    "passport_version": "1.0",
    "schema_version": 2,
    "status": "paper_live",
    "lineage_root": "psp_01HZX...",
    "parent_passport_id": null,
    "created_at": "2026-04-04T10:00:00Z",
    "created_by": "research_engine_v1",
    "origin": "generated",
    "validation_stage_reached": 4,
    "latest_backtest_run_id": "exp-2026-04-04-001",
    "latest_paper_run_id": "run-2026-04-15-batch1",
    "production_since": null,
    "retired_at": null,
    "retire_reason": null,
    "file_path": "generated/ema_crossover/fast_12_26-v1.0.json",
    "tags": ["batch1", "trend_family"]
}
```

---

## 6. Deployment & Portfolio Construction

### 6.1 Live Execution Pipeline

```
Registry (status: paper_live | production)
    │
    ▼
Scheduler / Orchestrator
    │ • load registry
    │ • manage scan cycles
    │ • dispatch to workers
    │ • retry policy per passport
    │ • rate limit handling
    │ • per-passport timeout
    │ • graceful degradation (one error ≠ batch failure)
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
Worker A       Worker B       Worker C
(passports     (passports     (passports
 group 1)       group 2)       group 3)
    │              │              │
    └──────────────┼──────────────┘
                   ▼
           Order Intent Layer
           (aggregate all intents)
                   │
                   ▼
           Portfolio Risk Manager
           (approve / resize / reject / queue)
                   │
                   ▼
           Execution Engine
           (paper fills OR exchange API)
                   │
                   ▼
           State DB + Telegram + Health Monitor
```

### 6.2 Portfolio Risk Manager

#### Hard Limits (auto-action)

| Control | Rule | Action |
|---------|------|--------|
| Total exposure cap | Gross notional < 60% of account | Reject new intents |
| Risk-weighted exposure cap | Vol-adjusted exposure < threshold | Reject/resize |
| DD circuit breaker | Live DD > max(15%, 1.5× backtest MaxDD) | Auto-pause strategy |
| Family cap | Max 3 strategies from same family | Reject lowest-priority |
| Cluster cap | Max 3 strategies per correlation cluster | Reject redundant |
| Emergency pause | Manual trigger or critical error | Halt all execution |

#### Soft Alerts (notify, don't auto-act)

| Monitor | Trigger | Action |
|---------|---------|--------|
| Correlation drift | Live correlation > backtest + 0.2 | Telegram alert |
| DD coincidence drift | Synchronized drawdowns detected | Telegram alert |
| Position overlap drift | Unexpected same-direction clustering | Telegram alert |
| Turnover anomaly | Unusual trade frequency | Telegram alert |
| Slippage anomaly | Fill quality degradation | Telegram alert |
| Live vs backtest divergence | Metrics outside expected bounds | Telegram alert |

#### Exposure Definition

Two metrics tracked simultaneously:
- **Gross notional exposure**: sum of all position notional values / account equity
- **Risk-weighted exposure**: each position weighted by realized volatility (20% allocation in high-vol ≠ 20% in low-vol)

Initial allocation: **equal risk parity** based on stop distance / realized vol. Evolution path: inverse-vol weighting → full risk parity.

If vol estimates unreliable early on, fallback to **fixed fractional + family caps**.

### 6.3 Paper vs Production Separation

Strict namespace isolation:

| Dimension | Paper | Production |
|-----------|-------|------------|
| Account namespace | `paper_*` | `prod_*` |
| Position tables | `positions_paper` | `positions_prod` |
| DB prefix | `paper.` | `prod.` |
| Telegram prefix | `[PAPER]` | `[PROD]` |
| Execution engine | Simulated fills | Exchange API |

No shared mutable state between paper and production.

### 6.4 Promotion Gate

`/promote` triggers policy check, not direct action:

1. ✅ Stage 4 evaluation passed
2. ✅ Minimum 14 days paper trading
3. ✅ Minimum trades met (family-specific, e.g., ≥10)
4. ✅ No catastrophic divergence from backtest expectation
5. ✅ Strategy not currently paused
6. ✅ Portfolio risk constraints still valid with addition
7. ✅ Family cap and cluster cap not exceeded

All checks must pass. Promotion = **assign passport version to production deployment slot** (not a binary status flip).

### 6.5 Telegram Integration

**Existing (keep):**
- Signal notifications with TP/SL threading
- `/status`, `/ping`, `/summary`

**New commands:**
| Command | Function |
|---------|----------|
| `/strategies` | List all live passports + status + PnL |
| `/compare <a> <b>` | Head-to-head paper performance |
| `/promote <id>` | Trigger promotion policy check |
| `/pause <id>` | Emergency pause (immediate) |
| `/health` | Operational health dashboard |
| Daily digest | Auto: portfolio metrics + per-strategy contribution |

### 6.6 Operational Health Monitor

| Metric | Check |
|--------|-------|
| Last scan timestamp | Alert if > 2× expected interval |
| Last bar processed | Detect stale data |
| API latency | Alert on degradation |
| API error rate | Alert on elevated failures |
| Telegram heartbeat | Confirm notification delivery |
| DB write health | Alert on failures |
| Runner process health | Confirm workers alive |

### 6.7 Deployment Topology

```
MacBook (local):
  ├── Strategy Research Engine
  │   ├── Generate passports (23 families → 300-500 candidates)
  │   ├── Run 4-stage evaluation pipeline
  │   └── Select portfolio
  ├── Experiment analysis
  └── Development

fight-tres (VPS):
  ├── Orchestrator + Workers (systemd)
  ├── Paper trading (all paper_live passports)
  ├── Production trading (promoted passports)
  ├── State DB (SQLite, namespaced tables)
  ├── Telegram bot
  └── Health monitor

Artifact handoff (local → VPS):
  ├── Passport bundle (generated/*.json)
  ├── Registry diff (registry.json changes)
  ├── Experiment result snapshot
  └── Promotion manifest
```

### 6.8 SQLite Schema (State DB on VPS)

Conceptual table separation:

| Table Group | Tables |
|-------------|--------|
| Passport state | `passports`, `passport_state` |
| Trading | `positions_paper`, `positions_prod`, `fills`, `trades` |
| Portfolio | `portfolio_snapshots`, `equity_curves` |
| Monitoring | `alerts`, `health_heartbeats`, `error_log` |
| Lifecycle | `promotion_events`, `retirement_events` |
| Experiment | `experiment_runs`, `experiment_metrics` |

### 6.9 Go-Live Sequence

1. Generate passports from 23 families → 300-500 candidates
2. Run 4-stage pipeline locally → 10-20 survivors
3. **Freeze experiment artifact** — record accepted survivor set
4. Deploy survivors to fight-tres as `paper_live`
5. Run 14d+ paper period
6. Evaluate each against promotion gate
7. **Run portfolio-level check** — verify combined risk constraints
8. Promote winners to `production` deployment slots
9. Continuous monitoring via Portfolio Risk Manager + Health Monitor

---

## 7. Open Items & Future Work

### Required Before Implementation
- [ ] RSI per-passport thresholds (currently hardcoded in `config.py` L17-18)
- [ ] Trailing stop formula fix (`trail_dist = N × ATR` instead of entry-SL distance)
- [ ] Investigate Dynamic v0.2 = Momentum v0.2 identical backtest results

### Phase 2 Enhancements
- Inverse-vol / full risk parity allocation (after enough live data)
- Adaptive regime classifier (ML-based, trained on longer history)
- Cross-exchange arbitrage families
- Orderbook imbalance strategies (requires L2 data)
- Portfolio rebalancing automation (periodic re-evaluation + rotation)

### Data Requirements
- 300+ days historical OHLCV (1H minimum, 15m and 4H for multi-TF families)
- Funding rate history (8h intervals)
- Open interest history (for OI divergence family)
- Liquidation data (for cascade family — may need external source)

---

## Appendix A: Reference Materials

Based on "151 Trading Strategies" (Kakushadze & Serur, 2018) at `~/fight/trading/reference/agentic/`:

**Directly applicable families:**
- Momentum (multiple variants: time-series, cross-sectional)
- Mean-reversion (Bollinger, RSI extremes, funding rate)
- Breakout / volatility expansion
- Carry (funding rate as crypto carry)
- Volume-based (OBV, VWAP, volume profile)
- Multi-factor (combining orthogonal signals)

**Key insight from reference:** Most published strategies have thin edges that disappear after transaction costs. The 4-stage filter is specifically designed to catch this — Stage 1 fee check + Stage 3 perturbation test together eliminate fragile edges.

# Passport Version Registry

> Auto-maintained alongside passport JSON configs.
> Source of truth for tracking strategy evolution and performance.

## How Versioning Works

- Each passport JSON contains a `version` field (semver: `major.minor`) and a `changelog` array.
- `major` bumps when the strategy's **thesis changes** (e.g., trend-following → mean-reversion).
- `minor` bumps when **parameters are tuned** within the same thesis (weights, thresholds, filters).
- Backtest results fill in `backtest_180d` in the changelog entry after validation runs.
- Git history is the authoritative rollback mechanism — `git show <sha>:pumpradar-passports/configs/<file>`.

## Version Comparison Quick Reference

> Values will be updated after `run_passport_validation.py` completes.

| Passport      | v0.1 Return | v0.1 WR | v0.2 Return | v0.2 WR | Δ Return | Status  |
|---------------|-------------|---------|-------------|---------|----------|---------|
| 🏆 OG         | pending     | pending | pending     | pending | pending  | pending |
| 💎 HiddenGem  | pending     | pending | pending     | pending | pending  | pending |
| 🚀 Momentum   | pending     | pending | pending     | pending | pending  | pending |
| 🎯 Dynamic    | pending     | pending | pending     | pending | pending  | pending |
| 🔄 Reversal   | pending     | pending | pending     | pending | pending  | pending |
| 🎯 Sniper     | pending     | pending | pending     | pending | pending  | pending |
| 📢 VolumeKing | pending     | pending | pending     | pending | pending  | pending |

## Per-Passport Changelog Summary

### 🏆 OG (`og_original.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Raised VOLUME_SPIKE_THRESHOLD 1.5→2.0 per grid search optimization (+49% vs +11%) |

### 💎 HiddenGem (`hidden_gem.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Added pressure=0.5 tiebreaker, raised ema_trend 1.0→1.5, added CONFIDENCE_THRESHOLD 58 |

### 🚀 Momentum (`momentum.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | EMA emphasis (ema=2.0), reduced noise indicators, raised threshold 54→60, capped positions 50→30 |

### 🎯 Dynamic (`dynamic_exit.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Disabled trailing stop (proven -63pp impact), aligned entry weights with Momentum v0.2 |

### 🔄 Reversal (`reversal.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial deployment — overtrade issue discovered in live (337 signals/3 days), quarantined |
| v0.2    | 2026-04-04 | Tightened quarantine: threshold 60→85, vol 2.0→2.5x, positions 20→5, sideways 80→90; keep disabled |

### 🎯 Sniper (`sniper.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Added MACD confirmation (1.0), raised ema 1.0→1.5, lowered threshold 70→65 for achievable signals |

### 📢 VolumeKing (`volume_king.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Lowered vol threshold 2.5→2.0, reduced vol weight 3.0→2.5, added MACD=0.5 and pressure=0.5 |

## Rollback Instructions

```bash
# See any passport at a prior version
git show 950e0ec:pumpradar-passports/configs/og_original.json

# Roll back a single passport
git checkout 950e0ec -- pumpradar-passports/configs/og_original.json
git commit -m "revert(og): roll back to v0.1 — v0.2 underperformed in backtest"

# Roll back all passports to v0.1 baseline
git checkout 950e0ec -- pumpradar-passports/configs/
git commit -m "revert: roll back all passports to v0.1 baseline"
```

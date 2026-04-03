from bot.backtester import run_backtest

def walk_forward_validate(config_override: dict, symbols: list[str], interval: str, 
                          train_days=120, test_days=60) -> dict:
    """
    Validates a strategy configuration by walk-forward testing.
    Day 1-120: Training (Optimization Period)
    Day 121-180: Testing (Out-of-sample Period)
    
    Returns:
        train_result: backtest summary on day 1-120
        test_result:  backtest summary on day 121-180
        overfit_score: |train_sharpe - test_sharpe| / max(train_sharpe, 0.1)
        verdict: KEEP / TUNE / KILL
    """
    print(f"[WalkForward] Training phase ({train_days} days, ending {test_days} days ago)...")
    train_result = run_backtest(
        symbols, 
        interval, 
        days=train_days, 
        cfg_override=config_override,
        end_offset_days=test_days
    )
    
    print(f"[WalkForward] Testing phase ({test_days} days, up to today)...")
    test_result = run_backtest(
        symbols, 
        interval, 
        days=test_days, 
        cfg_override=config_override,
        end_offset_days=0
    )
    
    train_sharpe = train_result.get("sharpe", 0.0) or 0.0
    test_sharpe = test_result.get("sharpe", 0.0) or 0.0
    
    # Avoid div by zero
    denom = max(abs(train_sharpe), 0.1)
    overfit_score = abs(train_sharpe - test_sharpe) / denom
    
    test_return = test_result.get("return_pct", 0.0)
    
    # Verdict rules
    if overfit_score < 0.3 and test_return > 0:
        verdict = "KEEP"
    elif overfit_score <= 0.6 and test_return > 0:
        verdict = "TUNE"
    else:
        verdict = "KILL"
        
    return {
        "train_result": train_result,
        "test_result": test_result,
        "overfit_score": overfit_score,
        "verdict": verdict
    }

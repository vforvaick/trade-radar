from __future__ import annotations

import json
from pathlib import Path


def _sample_messages() -> list[dict[str, object]]:
    return [
        {
            "id": 101,
            "date": "2026-02-18T00:00:00+00:00",
            "text": (
                "SIGNAL DETECTED\n"
                "**Symbol:** #BTCUSDT\n"
                "**Entry:** `100`\n"
                "TP1: `110`\n"
                "TP2: `115`\n"
                "TP3: `120`\n"
                "**Stop Loss:** `95`\n"
                "Risk/Reward: 1:2.08\n"
                "Rec. Leverage: **5x**\n"
                "BTC Trend: Sideways\n"
                "GO Confidence: 65%\n"
                "AI Insight: EMA + RSI + Volume confluence. Confidence: 65% (Action: GO)\n"
            ),
        },
        {
            "id": 102,
            "date": "2026-02-18T00:05:00+00:00",
            "text": "**Symbol:** #1 LONG BTCUSDT\nTP1 DONE\nProfit:** `+10.0%`",
        },
        {
            "id": 201,
            "date": "2026-02-18T01:00:00+00:00",
            "text": (
                "SIGNAL DETECTED\n"
                "**Symbol:** #ETHUSDT\n"
                "**Entry:** `200`\n"
                "TP1: `190`\n"
                "TP2: `185`\n"
                "TP3: `180`\n"
                "**Stop Loss:** `210`\n"
                "Risk/Reward: 1:1.43\n"
                "Rec. Leverage: **4x**\n"
                "BTC Trend: Downtrend\n"
                "GO Confidence: 58%\n"
                "AI Insight: MACD bearish, RSI <50, sell pressure 76.4%). "
                "Confidence: 58% (Action: GO)\n"
            ),
        },
        {
            "id": 202,
            "date": "2026-02-18T01:20:00+00:00",
            "text": "**Symbol:** #2 SHORT ETHUSDT\nSL HIT\nLoss:** `-15.0%`",
        },
    ]


def test_research_pipeline_entrypoints_write_to_data_and_docs_paths(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts import analyze_stats, parse_signals, simulate_equity, validate_market

    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    data_dir.mkdir()
    docs_dir.mkdir()

    messages_path = data_dir / "all_messages.json"
    trade_ledger_path = data_dir / "trade_ledger.csv"
    validated_ledger_path = data_dir / "validated_ledger.csv"
    equity_summary_path = data_dir / "equity_summary.json"
    equity_plot_path = data_dir / "equity_curve.png"
    report_path = docs_dir / "analysis_report.md"
    spec_path = docs_dir / "strategy_spec.md"

    messages_path.write_text(json.dumps(_sample_messages()), encoding="utf-8")

    parse_signals.main(
        ["--input", str(messages_path), "--output", str(trade_ledger_path)]
    )
    assert trade_ledger_path.exists()

    def fake_get_klines(symbol: str, start_ts: int, end_ts: int):
        del end_ts
        entry_price = 100.0 if symbol == "BTCUSDT" else 200.0
        signal_ts = start_ts + 5 * 60 * 1000
        return [
            [
                signal_ts,
                str(entry_price),
                str(entry_price * 1.02),
                str(entry_price * 0.98),
                str(entry_price),
            ]
        ]

    monkeypatch.setattr(validate_market, "get_klines", fake_get_klines)
    validate_market.main(
        [
            "--input",
            str(trade_ledger_path),
            "--output",
            str(validated_ledger_path),
            "--sleep-seconds",
            "0",
        ]
    )
    assert validated_ledger_path.exists()

    simulate_equity.main(
        ["--input", str(validated_ledger_path), "--output", str(equity_summary_path)]
    )
    assert equity_summary_path.exists()
    summary = json.loads(equity_summary_path.read_text(encoding="utf-8"))
    assert summary["All signals"]["trades"] == 2

    analyze_stats.main(
        [
            "--ledger",
            str(validated_ledger_path),
            "--messages",
            str(messages_path),
            "--report",
            str(report_path),
            "--spec",
            str(spec_path),
            "--equity-plot",
            str(equity_plot_path),
        ]
    )

    assert equity_plot_path.exists()
    assert report_path.exists()
    assert spec_path.exists()

    report_text = report_path.read_text(encoding="utf-8")
    spec_text = spec_path.read_text(encoding="utf-8")
    assert "Canonical report generated from `data/validated_ledger.csv`" in report_text
    assert "Methodology: fixed 3% risk-per-trade simulation" in report_text
    assert "Entries validated against Binance: **2/2**" in report_text
    assert "Interpretation note: indicator counts and distances are observed measurements" in spec_text
    assert "Hypothesis from observed mentions" in spec_text
    assert "file:///" not in report_text
    assert "file:///" not in spec_text

    for legacy_name in (
        "trade_ledger.csv",
        "validated_ledger.csv",
        "equity_summary.json",
        "analysis_report.md",
        "strategy_spec.md",
        "equity_curve.png",
    ):
        assert not (tmp_path / legacy_name).exists()

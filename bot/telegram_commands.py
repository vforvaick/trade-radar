"""Telegram command formatters for strategy monitoring."""
from __future__ import annotations

from typing import Optional


def format_strategies_list(strategies: list[dict]) -> str:
    if not strategies:
        return "📋 No active strategies."
    lines = ["📋 *Active Strategies*", ""]
    for s in strategies:
        status = s.get("status", "unknown")
        emoji = {"production": "🟢", "paper_live": "🟡", "retired": "🔴"}.get(status, "⚪")
        pnl = s.get("pnl", 0)
        pnl_str = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
        lines.append(f"{emoji} `{s.get('id', '?')}` — {pnl_str} ({status})")
    return "\n".join(lines)


def format_compare(a: dict, b: dict) -> str:
    header = f"📊 *Compare: {a.get('id', '?')} vs {b.get('id', '?')}*\n"
    metrics = ["sharpe", "calmar", "max_dd", "total_return", "win_rate"]
    lines = [header]
    for m in metrics:
        va = a.get(m, "N/A")
        vb = b.get(m, "N/A")
        va_str = f"{va:.3f}" if isinstance(va, (int, float)) else str(va)
        vb_str = f"{vb:.3f}" if isinstance(vb, (int, float)) else str(vb)
        lines.append(f"  {m}: {va_str} vs {vb_str}")
    return "\n".join(lines)


def format_health(health: dict) -> str:
    ok = health.get("healthy", False)
    emoji = "✅" if ok else "❌"
    lines = [f"{emoji} *System Health*", ""]
    for check, result in health.get("checks", {}).items():
        c_emoji = "✅" if result.get("ok") else "❌"
        lines.append(f"  {c_emoji} {check}: {result.get('detail', '')}")
    return "\n".join(lines)


def format_promotion_check(result: dict) -> str:
    passed = result.get("passed", False)
    emoji = "🎉" if passed else "⚠️"
    lines = [f"{emoji} *Promotion Check: {result.get('passport_id', '?')}*", ""]
    for gate, detail in result.get("gates", {}).items():
        g_emoji = "✅" if detail.get("passed") else "❌"
        lines.append(f"  {g_emoji} {gate}: {detail.get('reason', '')}")
    return "\n".join(lines)


def format_daily_digest(digest: dict) -> str:
    lines = ["📈 *Daily Digest*", ""]
    lines.append(f"Total PnL: {digest.get('total_pnl', 0):+.2f}%")
    lines.append(f"Active: {digest.get('active', 0)} strategies")
    lines.append(f"Trades: {digest.get('trades_today', 0)}")
    if digest.get("alerts"):
        lines.append("")
        lines.append("⚠️ *Alerts:*")
        for a in digest["alerts"]:
            lines.append(f"  • {a}")
    return "\n".join(lines)

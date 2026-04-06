from __future__ import annotations

import pytest

from bot import main, main_multi
from scripts import fetch_deep, fetch_samples


@pytest.mark.parametrize("module", [main, main_multi])
def test_telegram_credentials_use_env_and_cli_overrides(module, monkeypatch):
    monkeypatch.setenv("CRYPTOPASS_TG_TOKEN", "env-token")
    monkeypatch.setenv("CRYPTOPASS_TG_CHAT", "env-chat")

    assert module.resolve_telegram_credentials() == ("env-token", "env-chat")
    assert module.resolve_telegram_credentials("cli-token", "cli-chat") == (
        "cli-token",
        "cli-chat",
    )


@pytest.mark.parametrize("module", [main, main_multi])
def test_telegram_credentials_can_disable_telegram_when_both_missing(module, monkeypatch):
    monkeypatch.delenv("CRYPTOPASS_TG_TOKEN", raising=False)
    monkeypatch.delenv("CRYPTOPASS_TG_CHAT", raising=False)

    assert module.resolve_telegram_credentials() == (None, None)


@pytest.mark.parametrize("module", [main, main_multi])
def test_telegram_credentials_fail_fast_when_partial(module, monkeypatch):
    monkeypatch.setenv("CRYPTOPASS_TG_TOKEN", "env-token")
    monkeypatch.setenv("CRYPTOPASS_TG_CHAT", "   ")

    with pytest.raises(SystemExit, match="Missing Telegram credentials"):
        module.resolve_telegram_credentials()


@pytest.mark.parametrize("module", [fetch_samples, fetch_deep])
def test_telethon_settings_use_env(module, monkeypatch):
    monkeypatch.setenv("CRYPTOPASS_TG_API_ID", "123456")
    monkeypatch.setenv("CRYPTOPASS_TG_API_HASH", "hash-value")
    monkeypatch.setenv("CRYPTOPASS_TG_SESSION", "session-name")

    assert module.load_telethon_settings() == (123456, "hash-value", "session-name")


@pytest.mark.parametrize("module", [fetch_samples, fetch_deep])
def test_telethon_settings_fail_fast_on_missing_or_invalid(module, monkeypatch):
    monkeypatch.setenv("CRYPTOPASS_TG_API_ID", "   ")
    monkeypatch.setenv("CRYPTOPASS_TG_API_HASH", "")
    monkeypatch.delenv("CRYPTOPASS_TG_SESSION", raising=False)

    with pytest.raises(SystemExit, match="Missing Telethon credentials"):
        module.load_telethon_settings()

    monkeypatch.setenv("CRYPTOPASS_TG_API_ID", "not-an-integer")
    monkeypatch.setenv("CRYPTOPASS_TG_API_HASH", "hash-value")
    monkeypatch.setenv("CRYPTOPASS_TG_SESSION", "session-name")

    with pytest.raises(SystemExit, match="CRYPTOPASS_TG_API_ID must be a valid integer"):
        module.load_telethon_settings()

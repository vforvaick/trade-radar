"""Shared Telethon environment loader for Cryptopass fetch scripts."""
from __future__ import annotations

import os


def load_telethon_settings() -> tuple[int, str, str]:
    api_id_raw = (os.environ.get("CRYPTOPASS_TG_API_ID") or "").strip()
    api_hash = (os.environ.get("CRYPTOPASS_TG_API_HASH") or "").strip()
    session_name = (os.environ.get("CRYPTOPASS_TG_SESSION") or "").strip()

    missing = [
        name
        for name, value in [
            ("CRYPTOPASS_TG_API_ID", api_id_raw),
            ("CRYPTOPASS_TG_API_HASH", api_hash),
            ("CRYPTOPASS_TG_SESSION", session_name),
        ]
        if not value
    ]
    if missing:
        raise SystemExit("Missing Telethon credentials. Set " + ", ".join(missing) + ".")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise SystemExit("CRYPTOPASS_TG_API_ID must be a valid integer.") from exc

    return api_id, api_hash, session_name

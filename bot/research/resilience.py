"""Resilient wrapper for Binance API calls during research.

Adds retry-with-backoff and connectivity-wait logic so the research
pipeline survives laptop sleep, WiFi drops, and Binance rate limits.
"""
from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

import requests

from bot import config

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Connectivity check
# ---------------------------------------------------------------------------

def is_binance_reachable(timeout: float = 5.0) -> bool:
    """Quick ping to Binance Futures /fapi/v1/ping."""
    try:
        resp = requests.get(
            f"{config.BINANCE_FUTURES_BASE}/fapi/v1/ping",
            timeout=timeout,
        )
        return resp.status_code == 200
    except Exception:
        return False


def wait_for_connectivity(
    check_interval: float = 30.0,
    max_wait: float = 3600.0,
) -> bool:
    """Block until Binance API is reachable. Returns True if connected, False if max_wait exceeded."""
    if is_binance_reachable():
        return True

    logger.warning("Binance API unreachable — waiting for connectivity (check every %.0fs, max %.0fs)...",
                   check_interval, max_wait)
    waited = 0.0
    while waited < max_wait:
        time.sleep(check_interval)
        waited += check_interval
        if is_binance_reachable():
            logger.info("Binance API reachable after %.0fs wait", waited)
            return True
        if int(waited) % 300 == 0:  # log every 5 min
            logger.info("Still waiting for connectivity... (%.0fs elapsed)", waited)

    logger.error("Binance API still unreachable after %.0fs — giving up", max_wait)
    return False


# ---------------------------------------------------------------------------
# Retry decorator for research backtest calls
# ---------------------------------------------------------------------------

RETRIABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectTimeout,
    ConnectionError,
    TimeoutError,
    OSError,
)


def resilient_call(
    func: Callable[..., T],
    *args,
    max_retries: int = 5,
    base_delay: float = 10.0,
    max_delay: float = 300.0,
    connectivity_wait: float = 3600.0,
    **kwargs,
) -> T:
    """Call `func` with retry + connectivity-wait on network errors.

    On network error:
      1. Wait for Binance connectivity (polls every 30s)
      2. Retry with exponential backoff (10s, 20s, 40s, 80s, 160s)
      3. After max_retries, raise the last exception

    Non-network exceptions propagate immediately.
    """
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except RETRIABLE_EXCEPTIONS as e:
            last_exc = e
            logger.warning(
                "Network error on attempt %d/%d for %s: %s",
                attempt, max_retries, func.__name__, e,
            )
            if attempt < max_retries:
                # First ensure we have connectivity
                wait_for_connectivity(
                    check_interval=30.0,
                    max_wait=connectivity_wait,
                )
                # Then apply backoff delay (rate limit cooldown)
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                logger.info("Retrying in %.0fs (attempt %d/%d)...", delay, attempt + 1, max_retries)
                time.sleep(delay)
        except Exception as e:
            # Check if it's a wrapped network error (e.g., from requests)
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                last_exc = e
                logger.warning(
                    "Possible network error on attempt %d/%d: %s",
                    attempt, max_retries, e,
                )
                if attempt < max_retries:
                    wait_for_connectivity(check_interval=30.0, max_wait=connectivity_wait)
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.info("Retrying in %.0fs...", delay)
                    time.sleep(delay)
            else:
                raise  # non-network error, propagate immediately

    raise last_exc  # type: ignore[misc]

"""Tests for rate-limit retry logic in data_fetcher."""
import pytest
from unittest.mock import patch, MagicMock
import requests

from bot.data_fetcher import fetch_klines


class TestRateLimitRetry:
    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_retries_on_429(self, mock_get, mock_sleep):
        """HTTP 429 triggers retry with backoff."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_429
        )

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = []
        resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [resp_429, resp_ok]

        result = fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)
        assert result.empty  # empty because json returns []
        assert mock_get.call_count == 2
        mock_sleep.assert_called()  # backoff sleep was called

    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_retries_on_418(self, mock_get, mock_sleep):
        """HTTP 418 (IP ban) triggers retry with backoff."""
        resp_418 = MagicMock()
        resp_418.status_code = 418
        resp_418.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_418
        )

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = []
        resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [resp_418, resp_ok]

        result = fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)
        assert mock_get.call_count == 2

    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_gives_up_after_max_retries(self, mock_get, mock_sleep):
        """After max retries, raises the error."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_429
        )

        mock_get.return_value = resp_429

        with pytest.raises(requests.exceptions.HTTPError):
            fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)

        assert mock_get.call_count == 6  # 1 initial + 5 retries

    @patch("bot.data_fetcher.requests.get")
    def test_no_retry_on_other_errors(self, mock_get):
        """Non-rate-limit errors propagate immediately."""
        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_400
        )

        mock_get.return_value = resp_400

        with pytest.raises(requests.exceptions.HTTPError):
            fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)

        assert mock_get.call_count == 1  # no retry

    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_retries_on_connection_error(self, mock_get, mock_sleep):
        """ConnectionError triggers retry."""
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = []
        resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection reset"),
            resp_ok,
        ]

        result = fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)
        assert mock_get.call_count == 2

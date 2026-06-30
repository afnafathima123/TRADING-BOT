"""
client.py — Low-level Binance Futures Testnet REST client.

Handles authentication (HMAC-SHA256 signature), request signing,
retry logic, and structured error reporting. All HTTP calls go
through _signed_request() so logging is centralised.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

from .logging_config import get_logger

logger = get_logger("client")

BASE_URL = "https://testnet.binancefuture.com"

_RETRY_CONFIG = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist={500, 502, 503, 504},
    allowed_methods={"GET", "POST", "DELETE"},
)


class BinanceAPIError(Exception):
    """Raised when the Binance API returns a non-2xx response or error payload."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance API error {code}: {message}")


class BinanceClient:
    """Authenticated wrapper around the Binance Futures Testnet REST API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 10,
    ):
        self.api_key = api_key or os.environ.get("BINANCE_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("BINANCE_API_SECRET", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "API key and secret are required. "
                "Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables, "
                "or pass them explicitly."
            )

        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": self.api_key})
        adapter = HTTPAdapter(max_retries=_RETRY_CONFIG)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        logger.info("BinanceClient initialised | base_url=%s", self.base_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sign(self, params: Dict[str, Any]) -> str:
        """Return HMAC-SHA256 hex-digest of the query string."""
        query = urllib.parse.urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _signed_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send an authenticated request to *endpoint*.

        - Injects `timestamp` and `signature` automatically.
        - Logs request params and raw response.
        - Raises BinanceAPIError on non-2xx or Binance error payload.
        """
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self._sign(params)

        url = f"{self.base_url}{endpoint}"
        logger.debug("REQUEST  | %s %s | params=%s", method, endpoint, params)

        try:
            if method.upper() == "POST":
                response = self._session.post(url, data=params, timeout=self.timeout)
            elif method.upper() == "GET":
                response = self._session.get(url, params=params, timeout=self.timeout)
            elif method.upper() == "DELETE":
                response = self._session.delete(url, params=params, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except requests.exceptions.ConnectionError as exc:
            logger.error("Network error | %s", exc)
            raise ConnectionError(f"Failed to reach Binance API: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out | %s", exc)
            raise TimeoutError(f"Request to Binance API timed out: {exc}") from exc

        logger.debug("RESPONSE | status=%s | body=%s", response.status_code, response.text[:500])

        try:
            data = response.json()
        except ValueError:
            logger.error("Non-JSON response | status=%s | body=%s", response.status_code, response.text[:200])
            response.raise_for_status()
            raise

        if isinstance(data, dict) and "code" in data and data["code"] != 200:
            logger.error("API error | code=%s | msg=%s", data.get("code"), data.get("msg"))
            raise BinanceAPIError(data["code"], data.get("msg", "Unknown error"))

        if not response.ok:
            logger.error("HTTP error | status=%s | body=%s", response.status_code, response.text[:200])
            response.raise_for_status()

        return data

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_server_time(self) -> int:
        """Return Binance server time in milliseconds (unsigned endpoint)."""
        url = f"{self.base_url}/fapi/v1/time"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["serverTime"]

    def get_exchange_info(self) -> Dict[str, Any]:
        """Return exchange info (unsigned)."""
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_account_info(self) -> Dict[str, Any]:
        """Return account balance and positions (signed)."""
        return self._signed_request("GET", "/fapi/v2/account")

    def place_order(self, **kwargs) -> Dict[str, Any]:
        """
        Place a futures order (signed POST to /fapi/v1/order).

        Keyword args map directly to Binance API parameters:
            symbol, side, type, quantity, price, stopPrice, timeInForce, etc.
        """
        return self._signed_request("POST", "/fapi/v1/order", params=kwargs)

    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an open order by ID."""
        return self._signed_request(
            "DELETE", "/fapi/v1/order", params={"symbol": symbol, "orderId": order_id}
        )

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Return all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._signed_request("GET", "/fapi/v1/openOrders", params=params)

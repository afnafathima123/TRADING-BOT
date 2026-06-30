"""
orders.py — Order placement logic.

This module acts as the bridge between the validated CLI parameters
and the raw BinanceClient. It builds the correct API payload for each
order type, calls the client, and returns a normalised result dict.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .client import BinanceClient, BinanceAPIError
from .validators import validate_all
from .logging_config import get_logger

logger = get_logger("orders")


def _build_payload(params: Dict[str, Any]) -> Dict[str, Any]:
    """Translate validated params into a Binance API order payload."""
    order_type = params["order_type"]

    payload: Dict[str, Any] = {
        "symbol": params["symbol"],
        "side": params["side"],
        "type": order_type,
        "quantity": params["quantity"],
    }

    if order_type == "MARKET":
        # Market orders: no price or TIF required
        pass

    elif order_type == "LIMIT":
        payload["price"] = params["price"]
        payload["timeInForce"] = "GTC"  # Good Till Cancelled

    elif order_type == "STOP_LIMIT":
        payload["price"] = params["price"]          # limit fill price
        payload["stopPrice"] = params["stop_price"] # trigger price
        payload["timeInForce"] = "GTC"
        payload["type"] = "STOP"                    # Binance uses STOP for stop-limit

    return payload


def _format_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the most useful fields from a raw API response."""
    return {
        "orderId": raw.get("orderId"),
        "clientOrderId": raw.get("clientOrderId"),
        "symbol": raw.get("symbol"),
        "side": raw.get("side"),
        "type": raw.get("type"),
        "status": raw.get("status"),
        "origQty": raw.get("origQty"),
        "executedQty": raw.get("executedQty"),
        "price": raw.get("price"),
        "avgPrice": raw.get("avgPrice"),
        "stopPrice": raw.get("stopPrice"),
        "timeInForce": raw.get("timeInForce"),
        "updateTime": raw.get("updateTime"),
    }


def place_order(
    client: BinanceClient,
    *,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float | str,
    price: Optional[float | str] = None,
    stop_price: Optional[float | str] = None,
) -> Dict[str, Any]:
    """
    Validate inputs, build the payload, call the API, and return a
    normalised result dict.

    Raises:
        ValueError        — invalid input parameters
        BinanceAPIError   — API returned a business-logic error
        ConnectionError   — network failure
        TimeoutError      — request timed out
    """
    # 1. Validate
    params = validate_all(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
    )

    # 2. Build payload
    payload = _build_payload(params)

    # 3. Log intent
    logger.info(
        "Placing order | type=%s side=%s symbol=%s qty=%s price=%s stop=%s",
        params["order_type"],
        params["side"],
        params["symbol"],
        params["quantity"],
        params.get("price"),
        params.get("stop_price"),
    )

    # 4. Send to Binance
    raw_response = client.place_order(**payload)

    # 5. Log raw response summary
    logger.info(
        "Order response | orderId=%s status=%s executedQty=%s avgPrice=%s",
        raw_response.get("orderId"),
        raw_response.get("status"),
        raw_response.get("executedQty"),
        raw_response.get("avgPrice"),
    )

    return _format_result(raw_response)

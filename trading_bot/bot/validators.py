"""
validators.py — Input validation for trading parameters.
All functions raise ValueError with a human-readable message on failure.
"""

from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Optional


VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LIMIT"}


def validate_symbol(symbol: str) -> str:
    """Ensure symbol is a non-empty uppercase alphanumeric string."""
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Symbol cannot be empty.")
    if not symbol.isalnum():
        raise ValueError(f"Symbol '{symbol}' must be alphanumeric (e.g. BTCUSDT).")
    return symbol


def validate_side(side: str) -> str:
    """Ensure order side is BUY or SELL."""
    side = side.strip().upper()
    if side not in VALID_SIDES:
        raise ValueError(f"Side must be one of {VALID_SIDES}, got '{side}'.")
    return side


def validate_order_type(order_type: str) -> str:
    """Ensure order type is MARKET, LIMIT, or STOP_LIMIT."""
    order_type = order_type.strip().upper()
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Order type must be one of {VALID_ORDER_TYPES}, got '{order_type}'."
        )
    return order_type


def validate_quantity(quantity: str | float) -> float:
    """Ensure quantity is a positive number."""
    try:
        qty = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")
    if qty <= 0:
        raise ValueError(f"Quantity must be positive, got {qty}.")
    return float(qty)


def validate_price(price: Optional[str | float], required: bool = False) -> Optional[float]:
    """Validate price when present. Required for LIMIT and STOP_LIMIT orders."""
    if price is None or str(price).strip() == "":
        if required:
            raise ValueError("Price is required for LIMIT / STOP_LIMIT orders.")
        return None
    try:
        p = Decimal(str(price))
    except InvalidOperation:
        raise ValueError(f"Price '{price}' is not a valid number.")
    if p <= 0:
        raise ValueError(f"Price must be positive, got {p}.")
    return float(p)


def validate_stop_price(stop_price: Optional[str | float], required: bool = False) -> Optional[float]:
    """Validate stop price — required for STOP_LIMIT orders."""
    if stop_price is None or str(stop_price).strip() == "":
        if required:
            raise ValueError("Stop price is required for STOP_LIMIT orders.")
        return None
    try:
        sp = Decimal(str(stop_price))
    except InvalidOperation:
        raise ValueError(f"Stop price '{stop_price}' is not a valid number.")
    if sp <= 0:
        raise ValueError(f"Stop price must be positive, got {sp}.")
    return float(sp)


def validate_all(
    *,
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: Optional[str | float] = None,
    stop_price: Optional[str | float] = None,
) -> dict:
    """
    Run all validations and return a clean parameter dict.
    Raises ValueError on the first failure encountered.
    """
    order_type_clean = validate_order_type(order_type)
    requires_price = order_type_clean in {"LIMIT", "STOP_LIMIT"}
    requires_stop = order_type_clean == "STOP_LIMIT"

    return {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "order_type": order_type_clean,
        "quantity": validate_quantity(quantity),
        "price": validate_price(price, required=requires_price),
        "stop_price": validate_stop_price(stop_price, required=requires_stop),
    }

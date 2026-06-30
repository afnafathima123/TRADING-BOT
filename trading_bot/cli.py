#!/usr/bin/env python3
"""
cli.py — Command-line interface for the Binance Futures Trading Bot.

Usage examples:
  python cli.py place --symbol BTCUSDT --side BUY  --type MARKET --quantity 0.001
  python cli.py place --symbol ETHUSDT --side SELL --type LIMIT  --quantity 0.01 --price 3200
  python cli.py place --symbol BTCUSDT --side BUY  --type STOP_LIMIT --quantity 0.001 --price 65000 --stop-price 64500
  python cli.py account
  python cli.py open-orders --symbol BTCUSDT
"""

from __future__ import annotations

import argparse
import json
import sys
import os

from bot.logging_config import setup_logging, get_logger
from bot.client import BinanceClient, BinanceAPIError
from bot.orders import place_order

logger = get_logger("cli")


# ──────────────────────────────────────────────
# Printer helpers
# ──────────────────────────────────────────────

def print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


def print_order_summary(symbol, side, order_type, quantity, price=None, stop_price=None) -> None:
    print_separator()
    print("  ORDER REQUEST SUMMARY")
    print_separator()
    print(f"  Symbol     : {symbol}")
    print(f"  Side       : {side}")
    print(f"  Type       : {order_type}")
    print(f"  Quantity   : {quantity}")
    if price:
        print(f"  Price      : {price}")
    if stop_price:
        print(f"  Stop Price : {stop_price}")
    print_separator()


def print_order_result(result: dict) -> None:
    print()
    print_separator()
    print("  ORDER RESPONSE")
    print_separator()
    for key, value in result.items():
        if value is not None and value != "":
            print(f"  {key:<18}: {value}")
    print_separator()


# ──────────────────────────────────────────────
# Sub-command handlers
# ──────────────────────────────────────────────

def cmd_place(args: argparse.Namespace, client: BinanceClient) -> None:
    """Handle the 'place' sub-command."""
    print_order_summary(
        symbol=args.symbol,
        side=args.side.upper(),
        order_type=args.type.upper(),
        quantity=args.quantity,
        price=args.price,
        stop_price=args.stop_price,
    )

    try:
        result = place_order(
            client,
            symbol=args.symbol,
            side=args.side,
            order_type=args.type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
        )
        print_order_result(result)
        print("\n  ✅  Order placed successfully!\n")
        logger.info("CLI: order placed successfully | orderId=%s", result.get("orderId"))

    except ValueError as exc:
        print(f"\n  ❌  Validation error: {exc}\n", file=sys.stderr)
        logger.error("CLI: validation error | %s", exc)
        sys.exit(1)

    except BinanceAPIError as exc:
        print(f"\n  ❌  Binance API error [{exc.code}]: {exc.message}\n", file=sys.stderr)
        logger.error("CLI: API error | code=%s | %s", exc.code, exc.message)
        sys.exit(1)

    except (ConnectionError, TimeoutError) as exc:
        print(f"\n  ❌  Network error: {exc}\n", file=sys.stderr)
        logger.error("CLI: network error | %s", exc)
        sys.exit(1)


def cmd_account(args: argparse.Namespace, client: BinanceClient) -> None:
    """Handle the 'account' sub-command."""
    try:
        info = client.get_account_info()
        assets = [a for a in info.get("assets", []) if float(a.get("walletBalance", 0)) > 0]
        print_separator()
        print("  ACCOUNT BALANCES (non-zero)")
        print_separator()
        for asset in assets:
            print(f"  {asset['asset']:<8} wallet={asset['walletBalance']:>16}  unrealised PnL={asset.get('unrealizedProfit', '0'):>12}")
        print_separator()
    except BinanceAPIError as exc:
        print(f"\n  ❌  {exc}\n", file=sys.stderr)
        sys.exit(1)


def cmd_open_orders(args: argparse.Namespace, client: BinanceClient) -> None:
    """Handle the 'open-orders' sub-command."""
    try:
        orders = client.get_open_orders(symbol=args.symbol)
        if not orders:
            print("\n  No open orders.\n")
            return
        print_separator()
        print(f"  OPEN ORDERS  ({len(orders)} total)")
        print_separator()
        for o in orders:
            print(
                f"  [{o.get('orderId')}] {o.get('symbol')} {o.get('side')} {o.get('type')}"
                f"  qty={o.get('origQty')}  price={o.get('price')}  status={o.get('status')}"
            )
        print_separator()
    except BinanceAPIError as exc:
        print(f"\n  ❌  {exc}\n", file=sys.stderr)
        sys.exit(1)


# ──────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        description="Binance Futures Testnet Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Binance API key (or set BINANCE_API_KEY env var)",
    )
    parser.add_argument(
        "--api-secret",
        default=None,
        help="Binance API secret (or set BINANCE_API_SECRET env var)",
    )

    sub = parser.add_subparsers(dest="command", required=True, title="commands")

    # -- place -------------------------------------------------------
    place_p = sub.add_parser("place", help="Place a new order")
    place_p.add_argument("--symbol",     required=True,  help="e.g. BTCUSDT")
    place_p.add_argument("--side",       required=True,  choices=["BUY", "SELL", "buy", "sell"])
    place_p.add_argument("--type",       required=True,  choices=["MARKET", "LIMIT", "STOP_LIMIT",
                                                                   "market", "limit", "stop_limit"])
    place_p.add_argument("--quantity",   required=True,  type=float, help="Order quantity")
    place_p.add_argument("--price",      default=None,   type=float, help="Limit price (required for LIMIT/STOP_LIMIT)")
    place_p.add_argument("--stop-price", default=None,   type=float, help="Stop trigger price (required for STOP_LIMIT)")

    # -- account -----------------------------------------------------
    sub.add_parser("account", help="Show account balances")

    # -- open-orders -------------------------------------------------
    oo_p = sub.add_parser("open-orders", help="List open orders")
    oo_p.add_argument("--symbol", default=None, help="Filter by symbol (optional)")

    return parser


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger.info("Trading bot started | command=%s", args.command)

    try:
        client = BinanceClient(api_key=args.api_key, api_secret=args.api_secret)
    except ValueError as exc:
        print(f"\n  ❌  Configuration error: {exc}\n", file=sys.stderr)
        sys.exit(1)

    dispatch = {
        "place": cmd_place,
        "account": cmd_account,
        "open-orders": cmd_open_orders,
    }
    dispatch[args.command](args, client)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
dashboard.py — Real-time terminal dashboard.

Displays live price, RSI, signal, P&L, and a mini price bar chart
that refreshes every poll cycle using Python's curses library.

Run:
    python dashboard.py --symbol BTCUSDT
    python dashboard.py --symbol ETHUSDT --rsi-period 14 --interval 1m
"""

from __future__ import annotations

import argparse
import curses
import time
import sys
import os
from datetime import datetime
from typing import Optional

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.logging_config import setup_logging
from bot.strategy import RSIEngine


# ── Colour pair IDs ──────────────────────────────────────────────────
C_TITLE   = 1
C_GREEN   = 2
C_RED     = 3
C_YELLOW  = 4
C_CYAN    = 5
C_WHITE   = 6
C_DIM     = 7
C_BG_GRN  = 8
C_BG_RED  = 9
C_BG_YEL  = 10


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE,  curses.COLOR_CYAN,    -1)
    curses.init_pair(C_GREEN,  curses.COLOR_GREEN,   -1)
    curses.init_pair(C_RED,    curses.COLOR_RED,     -1)
    curses.init_pair(C_YELLOW, curses.COLOR_YELLOW,  -1)
    curses.init_pair(C_CYAN,   curses.COLOR_CYAN,    -1)
    curses.init_pair(C_WHITE,  curses.COLOR_WHITE,   -1)
    curses.init_pair(C_DIM,    curses.COLOR_WHITE,   -1)
    curses.init_pair(C_BG_GRN, curses.COLOR_BLACK,   curses.COLOR_GREEN)
    curses.init_pair(C_BG_RED, curses.COLOR_BLACK,   curses.COLOR_RED)
    curses.init_pair(C_BG_YEL, curses.COLOR_BLACK,   curses.COLOR_YELLOW)


def safe_addstr(win, y, x, text, attr=0):
    """Write to curses window without crashing on boundary overflow."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    max_len = w - x - 1
    if max_len <= 0:
        return
    try:
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def draw_box_title(win, y, x, title: str):
    attr = curses.color_pair(C_TITLE) | curses.A_BOLD
    safe_addstr(win, y, x, f"┌─ {title} ", attr)


def draw_rsi_bar(win, y, x, rsi: float, width: int = 30):
    """Visual RSI bar with colour zones."""
    filled = int((rsi / 100) * width)
    bar = "█" * filled + "░" * (width - filled)

    if rsi <= 30:
        color = curses.color_pair(C_GREEN)
    elif rsi >= 70:
        color = curses.color_pair(C_RED)
    else:
        color = curses.color_pair(C_YELLOW)

    safe_addstr(win, y, x, f"[{bar}] {rsi:5.1f}", color | curses.A_BOLD)
    # Zone markers
    safe_addstr(win, y + 1, x, f" ↑30{'':>{int(width*0.4)}}70↑", curses.color_pair(C_DIM))


def draw_mini_chart(win, y, x, candles: list, width: int = 40, height: int = 6):
    """Draw a mini ASCII candlestick chart."""
    if not candles:
        return
    closes = [c["close"] for c in candles[-width:]]
    lo = min(closes)
    hi = max(closes)
    rng = hi - lo or 1

    safe_addstr(win, y, x, f"  Price chart  hi:{hi:,.0f}  lo:{lo:,.0f}",
                curses.color_pair(C_DIM))

    for i, price in enumerate(closes):
        norm = int(((price - lo) / rng) * (height - 1))
        col = curses.color_pair(C_GREEN) if i == 0 or price >= closes[i - 1] else curses.color_pair(C_RED)
        for row in range(height):
            ch = "█" if row == (height - 1 - norm) else " "
            safe_addstr(win, y + 1 + row, x + i, ch, col)


def signal_attr(signal: str):
    if signal == "BUY":
        return curses.color_pair(C_BG_GRN) | curses.A_BOLD
    if signal == "SELL":
        return curses.color_pair(C_BG_RED) | curses.A_BOLD
    return curses.color_pair(C_BG_YEL) | curses.A_BOLD


def render(stdscr, snapshot: dict, symbol: str, last_update: str):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    price      = snapshot["price"]
    change_pct = snapshot["change_pct"]
    rsi        = snapshot["rsi"]
    signal     = snapshot["signal"]
    position   = snapshot["position"]
    pnl        = snapshot["pnl"]
    trades     = snapshot["trade_count"]
    high       = snapshot["high_24h"]
    low        = snapshot["low_24h"]
    candles    = snapshot["candles"]

    # ── Header ──────────────────────────────────────────────────────
    header = f"  ⚡ BINANCE FUTURES LIVE  |  {symbol}  |  {last_update}  "
    safe_addstr(stdscr, 0, 0, header.ljust(w), curses.color_pair(C_TITLE) | curses.A_BOLD | curses.A_REVERSE)

    # ── Price block ─────────────────────────────────────────────────
    draw_box_title(stdscr, 2, 2, "PRICE")
    price_col = curses.color_pair(C_GREEN) if change_pct >= 0 else curses.color_pair(C_RED)
    safe_addstr(stdscr, 3, 4, f"${price:>14,.2f}", price_col | curses.A_BOLD)
    sign = "+" if change_pct >= 0 else ""
    safe_addstr(stdscr, 4, 4, f"  24h: {sign}{change_pct:.2f}%", price_col)
    safe_addstr(stdscr, 5, 4, f"  Hi: {high:,.2f}   Lo: {low:,.2f}", curses.color_pair(C_DIM))

    # ── RSI block ───────────────────────────────────────────────────
    draw_box_title(stdscr, 7, 2, "RSI (14)")
    if rsi is not None:
        draw_rsi_bar(stdscr, 8, 4, rsi, width=28)
        zone = "OVERSOLD ← BUY" if rsi <= 30 else ("OVERBOUGHT → SELL" if rsi >= 70 else "NEUTRAL")
        safe_addstr(stdscr, 10, 4, f"  Zone: {zone}", curses.color_pair(C_DIM))
    else:
        safe_addstr(stdscr, 8, 4, "  Warming up… (need 15+ candles)", curses.color_pair(C_DIM))

    # ── Signal block ─────────────────────────────────────────────────
    draw_box_title(stdscr, 12, 2, "SIGNAL")
    sig_text = f"  ◆  {signal:^8}  ◆  "
    safe_addstr(stdscr, 13, 4, sig_text, signal_attr(signal))

    # ── P&L / Position block ─────────────────────────────────────────
    draw_box_title(stdscr, 15, 2, "PAPER P&L")
    pnl_col = curses.color_pair(C_GREEN) if pnl >= 0 else curses.color_pair(C_RED)
    safe_addstr(stdscr, 16, 4, f"  P&L    : {pnl:+.4f} USDT", pnl_col | curses.A_BOLD)
    safe_addstr(stdscr, 17, 4, f"  Trades : {trades}", curses.color_pair(C_WHITE))
    pos_col = curses.color_pair(C_GREEN) if position == "LONG" else curses.color_pair(C_DIM)
    safe_addstr(stdscr, 18, 4, f"  Pos    : {position}", pos_col | curses.A_BOLD)

    # ── Mini chart ───────────────────────────────────────────────────
    if w > 60:
        draw_box_title(stdscr, 2, 44, "PRICE CHART (last 30 candles)")
        draw_mini_chart(stdscr, 3, 46, candles, width=min(30, w - 50), height=8)

    # ── Footer ───────────────────────────────────────────────────────
    footer = "  [Q] Quit   [R] Reset P&L   RSI < 30 = BUY  |  RSI > 70 = SELL  "
    safe_addstr(stdscr, h - 1, 0, footer.ljust(w), curses.color_pair(C_DIM) | curses.A_REVERSE)

    stdscr.refresh()


def run_dashboard(stdscr, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    init_colors()

    setup_logging("WARNING")  # quiet during TUI

    latest: dict = {}
    lock = __import__("threading").Lock()

    def on_tick(snapshot):
        with lock:
            latest.clear()
            latest.update(snapshot)

    engine = RSIEngine(
        symbol=args.symbol,
        interval=args.interval,
        rsi_period=args.rsi_period,
        oversold=args.oversold,
        overbought=args.overbought,
        poll_interval=args.poll,
        on_tick=on_tick,
    )
    engine.start()

    try:
        while True:
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                with lock:
                    engine._pnl = 0.0
                    engine._trade_count = 0

            with lock:
                snap = dict(latest)

            if snap:
                ts = datetime.fromtimestamp(snap["timestamp"] / 1000).strftime("%H:%M:%S")
                render(stdscr, snap, args.symbol.upper(), ts)
            else:
                safe_addstr(stdscr, 2, 2, "  Connecting to Binance Testnet…", 0)
                stdscr.refresh()

            time.sleep(0.5)
    finally:
        engine.stop()


def main():
    parser = argparse.ArgumentParser(description="Live RSI Terminal Dashboard")
    parser.add_argument("--symbol",     default="BTCUSDT")
    parser.add_argument("--interval",   default="1m", choices=["1m","3m","5m","15m"])
    parser.add_argument("--rsi-period", default=14,  type=int)
    parser.add_argument("--oversold",   default=30,  type=float)
    parser.add_argument("--overbought", default=70,  type=float)
    parser.add_argument("--poll",       default=5,   type=int, help="Poll interval seconds")
    args = parser.parse_args()

    curses.wrapper(run_dashboard, args)


if __name__ == "__main__":
    main()

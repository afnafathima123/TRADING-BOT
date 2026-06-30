"""
strategy.py — Real-time RSI engine + signal generator.

Fetches live kline (candlestick) data from Binance Futures Testnet,
computes RSI, and emits BUY / SELL / HOLD signals.
"""

from __future__ import annotations

import time
import threading
import requests
from collections import deque
from typing import Callable, Optional
from .logging_config import get_logger

logger = get_logger("strategy")

BASE_URL = "https://testnet.binancefuture.com"


# ── RSI Calculation ──────────────────────────────────────────────────

def compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI over *period* bars. Returns None if not enough data."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def rsi_signal(rsi: float, oversold: float = 30, overbought: float = 70) -> str:
    """Return BUY / SELL / HOLD based on RSI thresholds."""
    if rsi <= oversold:
        return "BUY"
    if rsi >= overbought:
        return "SELL"
    return "HOLD"


# ── Live Price Fetcher ───────────────────────────────────────────────

def fetch_klines(symbol: str, interval: str = "1m", limit: int = 50) -> list[dict]:
    """Fetch recent closed candles from Binance Futures Testnet REST API."""
    url = f"{BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        raw = resp.json()
        candles = []
        for c in raw:
            candles.append({
                "open_time": c[0],
                "open":  float(c[1]),
                "high":  float(c[2]),
                "low":   float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "close_time": c[6],
            })
        return candles
    except Exception as exc:
        logger.error("fetch_klines error | %s", exc)
        return []


def fetch_ticker(symbol: str) -> Optional[dict]:
    """Fetch latest ticker (24h stats + last price) from REST API."""
    url = f"{BASE_URL}/fapi/v1/ticker/24hr"
    try:
        resp = requests.get(url, params={"symbol": symbol.upper()}, timeout=5)
        resp.raise_for_status()
        d = resp.json()
        return {
            "symbol":        d["symbol"],
            "last_price":    float(d["lastPrice"]),
            "price_change":  float(d["priceChangePercent"]),
            "high":          float(d["highPrice"]),
            "low":           float(d["lowPrice"]),
            "volume":        float(d["volume"]),
        }
    except Exception as exc:
        logger.error("fetch_ticker error | %s", exc)
        return None


# ── Live Strategy Engine ─────────────────────────────────────────────

class RSIEngine:
    """
    Polls Binance every *poll_interval* seconds, computes RSI,
    and calls *on_tick* with the latest market snapshot.

    on_tick signature:
        def on_tick(snapshot: dict) -> None
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1m",
        rsi_period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
        poll_interval: int = 5,
        on_tick: Optional[Callable] = None,
    ):
        self.symbol = symbol.upper()
        self.interval = interval
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.poll_interval = poll_interval
        self.on_tick = on_tick

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._entry_price: Optional[float] = None   # price when last BUY signal fired
        self._position: str = "NONE"                 # NONE / LONG / SHORT
        self._trade_count = 0
        self._pnl = 0.0

    # ── public ──────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("RSIEngine started | symbol=%s interval=%s period=%s",
                    self.symbol, self.interval, self.rsi_period)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("RSIEngine stopped")

    # ── internals ───────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                snapshot = self._tick()
                if snapshot and self.on_tick:
                    self.on_tick(snapshot)
            except Exception as exc:
                logger.error("RSIEngine loop error | %s", exc)
            time.sleep(self.poll_interval)

    def _tick(self) -> Optional[dict]:
        candles = fetch_klines(self.symbol, self.interval, limit=self.rsi_period + 5)
        ticker  = fetch_ticker(self.symbol)

        if not candles or not ticker:
            return None

        closes = [c["close"] for c in candles]
        rsi    = compute_rsi(closes, self.rsi_period)
        signal = rsi_signal(rsi, self.oversold, self.overbought) if rsi is not None else "HOLD"
        price  = ticker["last_price"]

        # Simple paper P&L tracking
        self._update_position(signal, price)

        latest_candle = candles[-1]
        return {
            "symbol":       self.symbol,
            "price":        price,
            "change_pct":   ticker["price_change"],
            "high_24h":     ticker["high"],
            "low_24h":      ticker["low"],
            "volume":       ticker["volume"],
            "rsi":          rsi,
            "signal":       signal,
            "position":     self._position,
            "pnl":          round(self._pnl, 4),
            "trade_count":  self._trade_count,
            "candle":       latest_candle,
            "candles":      candles[-30:],   # last 30 candles for chart
            "timestamp":    int(time.time() * 1000),
        }

    def _update_position(self, signal: str, price: float):
        """Paper-trade: track entry, exit, running P&L."""
        if signal == "BUY" and self._position == "NONE":
            self._position = "LONG"
            self._entry_price = price
            self._trade_count += 1
            logger.info("PAPER BUY  @ %.2f | RSI signal", price)

        elif signal == "SELL" and self._position == "LONG":
            pnl = price - self._entry_price
            self._pnl += pnl
            self._position = "NONE"
            self._entry_price = None
            self._trade_count += 1
            logger.info("PAPER SELL @ %.2f | P&L this trade: %.4f", price, pnl)

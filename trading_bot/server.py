#!/usr/bin/env python3
"""
server.py — Flask + SocketIO web dashboard server.

Pushes live RSI snapshots to the browser via WebSocket.
Also exposes a REST endpoint for placing paper/real orders.

Run:
    python server.py --symbol BTCUSDT --port 5000
Then open: http://localhost:5000
"""

from __future__ import annotations

import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

from bot.logging_config import setup_logging, get_logger
from bot.strategy import RSIEngine
from bot.client import BinanceClient, BinanceAPIError
from bot.orders import place_order
from bot.validators import validate_all

logger = get_logger("server")

app = Flask(__name__)
app.config["SECRET_KEY"] = "trading_bot_secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Globals (set at startup)
engine: RSIEngine = None
latest_snapshot: dict = {}
snap_lock = threading.Lock()


# ── Socket events ────────────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    logger.info("WebSocket client connected")
    with snap_lock:
        if latest_snapshot:
            emit("tick", latest_snapshot)


@socketio.on("disconnect")
def handle_disconnect():
    logger.info("WebSocket client disconnected")


# ── REST API ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/snapshot")
def api_snapshot():
    with snap_lock:
        return jsonify(latest_snapshot)


@app.route("/api/order", methods=["POST"])
def api_order():
    """Place an order via REST. Body: {symbol, side, type, quantity, price?, stop_price?}"""
    data = request.json or {}
    api_key    = data.get("api_key") or os.environ.get("BINANCE_API_KEY", "")
    api_secret = data.get("api_secret") or os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        return jsonify({"error": "API credentials missing. Set BINANCE_API_KEY / BINANCE_API_SECRET."}), 400

    try:
        validate_all(
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("type", ""),
            quantity=data.get("quantity", 0),
            price=data.get("price"),
            stop_price=data.get("stop_price"),
        )
        client = BinanceClient(api_key=api_key, api_secret=api_secret)
        result = place_order(
            client,
            symbol=data["symbol"],
            side=data["side"],
            order_type=data["type"],
            quantity=data["quantity"],
            price=data.get("price"),
            stop_price=data.get("stop_price"),
        )
        logger.info("REST order placed | %s", result)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except BinanceAPIError as exc:
        return jsonify({"error": f"[{exc.code}] {exc.message}"}), 502
    except Exception as exc:
        logger.exception("Unexpected order error")
        return jsonify({"error": str(exc)}), 500


# ── Engine callback ──────────────────────────────────────────────────

def on_tick(snapshot: dict):
    with snap_lock:
        latest_snapshot.clear()
        latest_snapshot.update(snapshot)
    # Push to all connected browser clients
    socketio.emit("tick", snapshot)
    logger.debug("Tick emitted | price=%s rsi=%s signal=%s",
                 snapshot.get("price"), snapshot.get("rsi"), snapshot.get("signal"))


# ── Entry point ──────────────────────────────────────────────────────

def main():
    global engine

    parser = argparse.ArgumentParser(description="Live RSI Web Dashboard Server")
    parser.add_argument("--symbol",     default="BTCUSDT")
    parser.add_argument("--interval",   default="1m", choices=["1m","3m","5m","15m"])
    parser.add_argument("--rsi-period", default=14,  type=int)
    parser.add_argument("--oversold",   default=30,  type=float)
    parser.add_argument("--overbought", default=70,  type=float)
    parser.add_argument("--poll",       default=5,   type=int)
    parser.add_argument("--port",       default=5000, type=int)
    parser.add_argument("--log-level",  default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger.info("Starting web dashboard | symbol=%s port=%s", args.symbol, args.port)

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

    print(f"\n  🚀  Dashboard running → http://localhost:{args.port}\n")
    socketio.run(app, host="0.0.0.0", port=args.port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()

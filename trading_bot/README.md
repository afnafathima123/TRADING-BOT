# Binance Futures Testnet Trading Bot

A clean, well-structured Python CLI application for placing orders on the **Binance Futures Testnet (USDT-M)**. Built for the Primetrade.ai Python Developer Intern assignment.

---

## Features

- **Market** and **Limit** orders (BUY / SELL)
- **Bonus: Stop-Limit** orders
- Clean CLI via `argparse` with validation feedback
- Separated **client layer** (auth, HTTP, retries) and **order layer** (business logic)
- Structured **logging** to rotating file + console
- Robust **error handling** (input validation, API errors, network failures)
- Account balance viewer and open-orders listing

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py
│   ├── client.py         # Binance REST client (HMAC auth, retries)
│   ├── orders.py         # Order placement & response normalisation
│   ├── validators.py     # Input validation (symbol, side, qty, price)
│   └── logging_config.py # Rotating file + console logger
├── cli.py                # CLI entry point (argparse)
├── logs/
│   └── trading_bot.log   # Rotating log file (auto-created)
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Create a Binance Futures Testnet account

1. Visit [https://testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Sign up / log in with GitHub
3. Navigate to **API Management** and generate a key pair
4. Copy your **API Key** and **API Secret**

### 2. Clone and install

```bash
git clone https://github.com/<your-username>/trading-bot.git
cd trading-bot

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Set credentials

**Option A — environment variables (recommended):**

```bash
export BINANCE_API_KEY="your_api_key_here"
export BINANCE_API_SECRET="your_api_secret_here"
```

**Option B — CLI flags:**

```bash
python cli.py --api-key YOUR_KEY --api-secret YOUR_SECRET place ...
```

---

## Usage

### Place a Market Order

```bash
# BUY 0.001 BTC at market price
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

# SELL 0.01 ETH at market price
python cli.py place --symbol ETHUSDT --side SELL --type MARKET --quantity 0.01
```

### Place a Limit Order

```bash
# BUY 0.001 BTC at $65,000
python cli.py place --symbol BTCUSDT --side BUY --type LIMIT --quantity 0.001 --price 65000

# SELL 0.01 ETH at $3,200
python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.01 --price 3200
```

### Place a Stop-Limit Order (Bonus)

```bash
# BUY 0.001 BTC; triggers at $64,500, fills at $65,000
python cli.py place \
  --symbol BTCUSDT \
  --side BUY \
  --type STOP_LIMIT \
  --quantity 0.001 \
  --price 65000 \
  --stop-price 64500
```

### View Account Balances

```bash
python cli.py account
```

### View Open Orders

```bash
python cli.py open-orders
python cli.py open-orders --symbol BTCUSDT
```

### Verbose / Debug Logging

```bash
python cli.py --log-level DEBUG place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

---

## Example Output

```
────────────────────────────────────────────────────────────
  ORDER REQUEST SUMMARY
────────────────────────────────────────────────────────────
  Symbol     : BTCUSDT
  Side       : BUY
  Type       : MARKET
  Quantity   : 0.001
────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────
  ORDER RESPONSE
────────────────────────────────────────────────────────────
  orderId           : 4751823
  symbol            : BTCUSDT
  side              : BUY
  type              : MARKET
  status            : FILLED
  origQty           : 0.001
  executedQty       : 0.001
  avgPrice          : 67345.10
────────────────────────────────────────────────────────────

  ✅  Order placed successfully!
```

---

## Logging

Logs are written to `logs/trading_bot.log` (rotating, max 5 × 5 MB).

Each line follows the format:
```
TIMESTAMP | LEVEL    | MODULE | message
```

Example:
```
2025-05-20T10:12:02 | INFO     | trading_bot.orders | Order response | orderId=4751823 status=FILLED executedQty=0.001 avgPrice=67345.10
```

---

## Error Handling

| Error Type | Behaviour |
|---|---|
| Invalid symbol / qty / price | Validation error printed; exit code 1 |
| API business error (e.g. insufficient margin) | Binance error code + message printed |
| Network failure | Connection error printed with retry details |
| Request timeout | Timeout error printed |

---

## Assumptions

- All orders use **Reduce-Only = false** (default) — suitable for opening positions
- Limit orders use **GTC** (Good Till Cancelled) time-in-force
- Quantities must satisfy the symbol's lot-size filter; the testnet is more lenient than mainnet
- API credentials are never logged (only a partial signature hex appears at DEBUG level)
- Python 3.9+ is assumed

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP client with retry adapter |

No external Binance SDK is used — all API calls are raw REST with HMAC-SHA256 signing.

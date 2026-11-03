# Binance Funding Rate Arbitrage Bot

Fully automated, market-neutral funding rate arbitrage bot for Binance Spot + USDT-M Futures.

## Strategy Summary

When perpetual funding rate is **significantly positive**:
- Buy the asset on **Spot**
- Short the same notional on **USDT-M Perpetual**
- Collect funding payments while staying roughly delta-neutral

When funding is **significantly negative** the opposite is done (requires margin shorting).

## Project Structure

```
binance_funding_arb/
├── config/
│   └── config.example.yaml     # Copy → config.yaml
├── src/
│   ├── data/
│   │   ├── exchange_client.py  # ccxt wrapper
│   │   └── market_data.py      # Funding + price collector
│   ├── strategy/
│   │   └── funding_arb.py      # Core signal logic
│   ├── execution/
│   │   └── executor.py         # Order placement & position mgmt
│   ├── risk/
│   │   └── risk_manager.py     # Circuit breakers + live liq check
│   ├── monitoring/
│   │   └── alerts.py           # Telegram (optional)
│   ├── web/
│   │   ├── app.py              # FastAPI dashboard
│   │   └── templates/
│   │       └── dashboard.html  # Live UI
│   ├── utils/
│   │   ├── config.py
│   │   ├── logger.py
│   │   ├── helpers.py
│   │   └── persistence.py      # SQLite position store
│   └── main.py                 # Entry point
├── logs/
├── data/
├── requirements.txt
├── .env.example
└── README.md
```

## Quick Start

### 1. Install dependencies

```bash
cd binance_funding_arb
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

Edit `config/config.yaml`:
- Put your Binance API key & secret (Read + Trade only, **no withdrawal**)
- Keep `testnet: true` and `dry_run: true` until confident
- Adjust symbols, position size, min funding APR, risk limits
- Dashboard on port **8080** by default

### 3. Run (paper / dry-run)

```bash
python -m src.main
```

Open dashboard: **http://localhost:8080**

### 4. Testnet then Mainnet

1. `dry_run: false`, keep `testnet: true`
2. Small size, monitor closely
3. Only then mainnet with tiny capital

## Safety Features

- Dry-run mode (no real orders)
- Testnet support
- Daily loss limit + max drawdown circuit breaker
- **Live liquidation distance monitoring** + auto-flatten
- Max open positions + max total exposure
- Net APR after fees (not raw funding)
- Delta rebalancing when hedge drifts
- State persistence (survives restart)
- Dynamic position sizing by funding strength
- Basis filter + min hold time
- Structured logging + optional Telegram alerts
- Live web dashboard

## Security Best Practices

1. API keys: **Read + Spot Trade + Futures only**. Never enable Withdrawals.
2. Enable **IP whitelist** on the Binance API key.
3. Prefer a **dedicated sub-account** for the bot.
4. Keep keys in `config.yaml` or `.env` — never commit them.
5. Start with `dry_run: true` + `testnet: true`.
6. Start with very small `position_size_usdt`.

## Important Warnings

- This is not financial advice. Crypto trading involves substantial risk of loss.
- Funding rates can flip. You can end up paying funding.
- Basis risk, liquidation risk, exchange risk remain.
- Never risk money you cannot afford to lose.

## License

For educational and personal use. Use at your own risk.

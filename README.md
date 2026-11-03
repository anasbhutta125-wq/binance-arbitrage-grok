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
│   │   └── risk_manager.py     # Circuit breakers
│   ├── monitoring/
│   │   └── alerts.py           # Telegram (optional)
│   ├── web/
│   │   ├── app.py              # FastAPI dashboard
│   │   └── templates/
│   │       └── dashboard.html  # Live UI
│   ├── utils/
│   │   ├── config.py
│   │   ├── logger.py
│   │   └── helpers.py
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
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

Edit `config/config.yaml`:
- Put your Binance API key & secret (create keys with **read + trade** only, **no withdrawal**)
- Keep `testnet: true` and `dry_run: true` until you are 100% confident
- Adjust symbols, position size, min funding APR, risk limits
- Dashboard runs on port **8080** by default (`monitoring.dashboard_port`)

### 3. Run (paper / dry-run)

```bash
python -m src.main
```

Then open the live dashboard in your browser:

```
http://localhost:8080
```

The dashboard auto-refreshes every 5 seconds and shows:
- Bot status (Running / Dry-Run / Testnet / Mainnet)
- Open positions & size
- Live funding rates + projected APR
- Basis, mark vs spot prices
- Risk status & daily PnL

### 4. Move to Testnet live orders

1. Set `dry_run: false`
2. Keep `testnet: true`
3. Fund your Binance Futures Testnet account
4. Run again and monitor closely

### 5. Mainnet (only after extensive testing)

1. Set `testnet: false`
2. Start with **very small** `position_size_usdt`
3. Monitor 24/7 for the first days

## Safety Features

- Dry-run mode (no real orders)
- Testnet support
- Daily loss limit
- Max drawdown circuit breaker
- Liquidation distance monitoring
- Max open positions
- Configurable min funding APR filter
- Basis filter (avoid wide basis)
- Structured logging + optional Telegram alerts

## Important Warnings

- **This is not financial advice.** Crypto trading involves substantial risk of loss.
- Funding rates can flip rapidly. You can end up paying funding instead of receiving it.
- You still face basis risk, liquidation risk, exchange risk, and operational risk.
- Start extremely small. Never risk money you cannot afford to lose.
- The negative-funding path (short spot) requires margin account and borrowing – implement and test carefully.
- Keep API keys secure. Never enable withdrawal permissions.
- Past performance of the strategy does not guarantee future results.

## Next Improvements (recommended)

- [ ] Full delta tracking & automatic rebalancing
- [ ] Historical funding backtester
- [ ] Web dashboard (FastAPI + simple frontend)
- [ ] Multi-exchange support
- [ ] Better short-spot / margin handling
- [ ] Funding rate prediction model
- [ ] Portfolio-level risk (correlation, concentration)

## License

For educational and personal use. Use at your own risk.

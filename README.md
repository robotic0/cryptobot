<div align="center">

# 💱 CryptoBot

**A custodial multi-currency wallet with a P2P escrow marketplace, for Telegram.**

Hold balances in several assets, browse peer-to-peer offers, and trade safely
through an escrow flow that locks the seller's crypto until the buyer's payment
is confirmed. Live market rates from CoinGecko, PIN-protected withdrawals, and a
full append-only ledger.

[![CI](https://github.com/robotic0/cryptobot/actions/workflows/ci.yml/badge.svg)](https://github.com/robotic0/cryptobot/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-2481cc.svg)](https://docs.aiogram.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

</div>

---

> ### ⚠️ Important — educational project
>
> CryptoBot implements the **architecture** of a custodial wallet and P2P
> exchange for learning and demonstration. It uses a **simulated internal
> ledger**: it does **not** custody real private keys, and deposits/withdrawals
> move balances *within this database only* — nothing is broadcast to any
> blockchain. Do not connect it to real funds. Market **prices** are real
> (read-only, via CoinGecko).

## ✨ Features

| | Feature | Description |
|---|---|---|
| 👛 | **Multi-currency wallet** | Per-user balances across BTC, ETH, USDT, BNB, SOL, TON, TRX, XRP, split into *available* and *escrow-locked*. |
| 🔒 | **Escrow-based P2P trading** | The seller's crypto is locked on trade start and only released to the buyer after payment is confirmed — or returned on cancel. |
| 📊 | **Live market rates** | Real USD prices from the CoinGecko public API (no key), cached with a short TTL. |
| 🧾 | **Append-only ledger** | Every balance movement is recorded as an immutable `LedgerEntry` — a full audit trail. |
| 🔐 | **PIN-protected actions** | Withdrawals require a PBKDF2-hashed transaction PIN; every check is audit-logged. |
| 💯 | **Exact-money arithmetic** | All amounts are `Decimal`, stored as text so **no float rounding** ever corrupts a balance. |

## 🔄 Escrow trade lifecycle

```
Buyer takes a SELL offer
        │
        ▼
  ESCROW_LOCKED ──(buyer sends fiat, taps "To'lovni tasdiqladim")──▶ FIAT_PAID
        │                                                                │
        │                                              (seller taps "Mablag'ni chiqarish")
        │                                                                ▼
   (either party cancels)                                           COMPLETED
        │                                                     crypto → buyer (minus fee)
        ▼
    CANCELLED
 crypto returned to seller
```

At `ESCROW_LOCKED` the seller's crypto leaves *available* and enters *locked*.
It can only ever go two ways: **released to the buyer** (on completion) or
**returned to the seller** (on cancel). This invariant is enforced in
[`app/services/wallet.py`](app/services/wallet.py) and covered by tests.

## 🏗️ Architecture

```
bot.py                     # entry point: bot + dispatcher + middleware
│
└── app/
    ├── config.py          # environment-driven configuration
    ├── database/          # async SQLAlchemy engine, models, DecimalText type
    ├── services/
    │   ├── wallet.py      # the custodial ledger (credit/debit/lock/unlock/release)
    │   ├── escrow.py      # P2P offers + trade state machine
    │   ├── rates.py       # CoinGecko rate client with caching
    │   └── security.py    # PBKDF2 PIN hashing + audit log
    ├── handlers/          # aiogram routers (start, wallet, market, trades)
    ├── keyboards/         # inline keyboards + callback factories
    ├── middlewares/        # per-update DB session + service injection
    ├── states/            # FSM flows (offer, withdraw, deposit, pin)
    └── utils/             # Decimal money helpers + logging
```

**Tech stack:** [aiogram 3.x](https://docs.aiogram.dev/) · [SQLAlchemy 2.0 (async)](https://www.sqlalchemy.org/) · [aiohttp](https://docs.aiohttp.org/) · SQLite / PostgreSQL.

## 🚀 Quick start

```bash
git clone https://github.com/robotic0/cryptobot.git
cd cryptobot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # add your BOT_TOKEN
python bot.py
```

## 🐳 Run with Docker

```bash
cp .env.example .env               # add your BOT_TOKEN
docker compose up -d --build
```

## 💬 Commands

| Command | Description |
|---|---|
| `/wallet` | Show balances (with USD estimate) |
| `/deposit` | Add funds (simulated) |
| `/withdraw` | Withdraw (PIN required) |
| `/setpin` | Set your transaction PIN |
| `/market` | Browse open P2P offers |
| `/sell` · `/buy` | Create a sell / buy offer |
| `/myoffers` | Your open offers |
| `/trades` | Your trades + actions |
| `/price` | Live market rates |
| `/cancel` | Cancel the current step |

## 🧪 Development

```bash
pip install -e ".[dev]"

ruff check .      # lint
pytest -q         # 23 tests: money, ledger and escrow lifecycle
```

The financial core is thoroughly tested — ledger atomicity, no-negative-balance
guarantees, value conservation with fees, and every escrow state transition
(happy path, cancel, dispute, partial fills, own-offer and overfill rejection) —
all with no network access.

## 🔐 Security notes

- PINs are hashed with **PBKDF2-HMAC-SHA256** (200k iterations, per-PIN salt)
  and verified in constant time.
- Balances can never go negative; every mutation is checked and logged.
- Amounts are `Decimal` end-to-end and stored as text to avoid float drift.
- This is a demo ledger — for real custody you would add HSM-backed key
  management, on-chain settlement, KYC/AML, and independent reconciliation.

## 🗺️ Roadmap

- [ ] Admin dispute-resolution console
- [ ] Real on-chain deposit detection (watch-only addresses)
- [ ] Order book & market orders alongside P2P
- [ ] Rate-limiting and 2FA
- [ ] Multi-language UI

## 📄 License

Distributed under the [MIT License](LICENSE).

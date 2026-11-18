# Plico Quoting Tool

A web tool that turns customer, site and commercial inputs into an **estimated Plico solar + battery proposal**: system, price after rebates, savings, payback, finance repayments and internal margin. It also says how reliable the quote is and which inputs are still missing.

> ⚠️ **All prices, STC factors, rebate amounts and finance rates in `config/pricing.json` are placeholders.** Replace them with figures from the Master Plico Quoting Tool and current Clean Energy Regulator / WA Government rules before quoting a customer.

## Features

| Area | What it does |
|---|---|
| Customer inputs | Bill, postcode, residential status, objective, payment preference |
| Technical inputs | Phase, roof type, storeys, panel location, existing solar/battery |
| Proposed system | Full System, Battery Only, Battery + Hybrid Inverter Replacement, Expansion; Energy Creator 10 / 10+ packages or custom |
| Commercial | System cost, markup or price override, solar STCs, battery STCs (tiered), WA battery rebate, VPP discount, promotions |
| Finance | Cash, Plico Finance, government interest-free loan, or both. **The interest-free loan is excluded from the Plico Finance amount and buyout.** |
| Savings | Usage estimated from the quarterly bill (or entered from the bill), generation, self-consumption, payback |
| Readiness | `Indicative` → `Estimated` → `Ready for firm quote`, with a list of missing inputs and warnings |
| Output | Print / save as PDF (internal margin hidden), JSON export, draft autosave in the browser |

## Quick start

```bash
git clone <repo-url> plico-quoting-tool
cd plico-quoting-tool
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python run.py
```

Open http://127.0.0.1:5000 and click **Load Parmelia example**.

## Project structure

```
plico-quoting-tool/
├── app/
│   ├── __init__.py          # Flask app factory + JSON API
│   ├── quote_engine.py      # All quote calculations (pure Python, no I/O)
│   ├── templates/index.html # Page
│   └── static/
│       ├── js/api.js        # API client + formatting helpers
│       ├── js/app.js        # Form handling and proposal rendering
│       └── css/styles.css
├── config/pricing.json      # Packages, costs, STCs, rebates, finance, savings assumptions
├── tests/                   # pytest suite (engine + API)
├── docs/CALCULATIONS.md     # How every number is worked out
├── .github/                 # CI workflow, PR + issue templates
├── run.py                   # Local dev server
└── requirements*.txt
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status and pricing config version |
| GET | `/api/config` | Packages, solution types, site adders, finance terms (no internal costs) |
| POST | `/api/quote` | Quote request JSON → proposal JSON. `422` with `{"error": ...}` on invalid input |

```bash
curl -X POST http://127.0.0.1:5000/api/quote -H "Content-Type: application/json" \
  -d '{"postcode":"6167","quarterly_bill":300,"package":"energy_creator_10","payment_type":"plico_finance"}'
```

## Updating pricing

Edit `config/pricing.json`, bump `version`, and open a PR using the **Pricing / rebate update** issue template. To use a different file without editing the committed one:

```bash
PLICO_PRICING_CONFIG=config/pricing.local.json python run.py
```

`pricing.local.json` is git-ignored so real commercial figures are not committed by accident.

## Tests

```bash
pytest -q
ruff check .
```

CI runs both on every push and pull request, plus a syntax check of the JavaScript.

## Deploying

For more than local use, run behind a production WSGI server, e.g. `pip install gunicorn && gunicorn "app:create_app()"`, and put it behind company sign-in: the API returns internal cost and margin.

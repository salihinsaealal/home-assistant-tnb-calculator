# TNB AFA Rate Scraper v3.1.0

A Docker service that fetches TNB's AFA (Automatic Fuel Adjustment) rates with **dual-strategy scraping** for reliability and instant API responses.

## Features

- **Dual Strategy**: Primary: fetches `rates.js` directly (authoritative JS source from TNB, < 1s). Fallback: Playwright headless browser
- **Smart Caching**: Daily refresh at 6am, keeps previous cache if new scrape fails
- **Instant Responses**: API calls return cached data (< 10ms)
- **Non-blocking Startup**: Server starts immediately, cache loads in background
- **Persistent Storage**: Cache survives container restarts
- **Manual Refresh**: Force re-scrape when needed

## Requirements

- Docker
- Docker Compose

## Quick Start

```bash
# Clone or copy this folder to your server
cd tnb-afa-scraper

# Build and run
docker compose up -d --build

# Check it's running (server responds instantly, cache loads in background)
docker logs -f tnb-afa-scraper

# Test health endpoint
curl http://localhost:8001/

# Test AFA endpoint (instant from cache)
curl http://localhost:8001/afa/simple
```

## API Endpoints

| Endpoint | Method | Description | Speed |
|----------|--------|-------------|-------|
| `/` | GET | Health check + cache status | Instant |
| `/afa/simple` | GET | Current month's AFA rate | Instant (cached) |
| `/afa/all` | GET | All AFA rates (all periods) | Instant (cached) |
| `/complete` | GET | Complete tariff data (AFA + base rates + ICT) | Instant (cached) |
| `/refresh` | GET | Force re-scrape all data | < 3s (rates.js) |
| `/debug` | GET | Debug info + raw scrape | Varies |

### Response Format (`/afa/simple`)

```json
{
    "afa_rate": 0.0359,
    "afa_rate_raw": 0.0359,
    "effective_date": "2026-07-01",
    "period": "Julai 2026",
    "last_scraped": "2026-07-14T06:00:00",
    "source": "rates.js"
}
```

- `afa_rate`: AFA rate in **RM/kWh** — **signed** (negative = rebate, positive = surcharge)
- `effective_date`: First day of the rate's effective month
- `period`: Human-readable month name
- `last_scraped`: When the data was last fetched from TNB
- `source`: Data source (`rates.js` or `playwright`)

**Note:** Unlike v3.0.0, the rate is now **signed** (not `abs()`). Negative = rebate, positive = surcharge. This matches the HA integration's calculation convention exactly.

## Home Assistant Integration

Once the scraper is running, use it with TNB Calculator:

```yaml
service: tnb_calculator.fetch_afa_rate
data:
  api_url: "http://<your-server-ip>:8001/afa/simple"
```

### Daily Automation (recommended)

```yaml
automation:
  - alias: "Update TNB AFA Rate Daily"
    trigger:
      - platform: time
        at: "06:05:00"
    action:
      - service: tnb_calculator.fetch_afa_rate
        data:
          api_url: "http://<your-server-ip>:8001/afa/simple"
```

## How It Works

### Primary Strategy (rates.js direct fetch)
1. Fetches `index.html` from TNB to discover the latest `rates.js?v=X.X.XX` URL
2. Downloads `rates.js` directly — no browser needed
3. Parses the `FUEL_BY_MONTH` JavaScript object (authoritative monthly AFA rates in RM/kWh)
4. Parses `DOMESTIC` and `DOMESTIC_TOU` constants for base tariff rates
5. Returns the rate matching the current month — **signed** (no `abs()`)

### Fallback Strategy (Playwright)
1. If `rates.js` fetch fails, falls back to Playwright (headless Chromium)
2. Loads the TNB tariff page and extracts table data
3. Parses rates and periods from page text

### Safety
- If validation fails on new scrape → keeps previous cache
- If both strategies fail → keeps previous cache
- Validation requires ≥3 rates, valid range, and current/prev month coverage

## Troubleshooting

### Check logs

```bash
docker logs tnb-afa-scraper
```

### Rebuild after changes

```bash
docker compose up -d --build
```

### Stop the service

```bash
docker compose down
```

## Technical Details

- **Version:** 3.1.0
- **Base Image:** `mcr.microsoft.com/playwright/python:v1.40.0-focal`
- **Framework:** FastAPI + Uvicorn
- **Primary method:** Direct HTTP fetch (`aiohttp`)
- **Fallback method:** Chromium headless (Playwright)
- **Port:** 8001 (mapped from 8000 in container - exposed on host port 8001 for external access)

# TNB AFA Rate Scraper

A Docker service that scrapes TNB's website for AFA (Automatic Fuel Adjustment) rates with **smart caching** for instant API responses.

## Features

- **Smart Caching**: Scrapes on startup, then automatically on 1st & 25th of each month
- **Instant Responses**: API calls return cached data (< 10ms)
- **Persistent Storage**: Cache survives container restarts
- **Manual Refresh**: Force re-scrape when needed

## Requirements

- Docker
- Docker Compose
- Ubuntu 24.04 LTS (tested on N150)

## Quick Start

```bash
# Clone or copy this folder to your server
cd tnb-afa-scraper

# Build and run
docker compose up -d --build

# Check it's running (first startup will scrape - takes ~30s)
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
| `/complete` | GET | Complete tariff data (AFA + base rates) | Instant (cached) |
| `/refresh` | GET | Force re-scrape all data | ~30s |
| `/debug` | GET | Debug info + full page text | ~30s |

### Response Format (`/afa/simple`)

```json
{
    "afa_rate": 0.0891,
    "afa_rate_raw": -0.0891,
    "effective_date": "2025-11-01",
    "last_scraped": "2025-11-28T09:29:08.975711"
}
```

- `afa_rate`: AFA rate in **RM/kWh** (converted from sen/kWh)
- `effective_date`: First day of the rate's effective month
- `last_scraped`: When the data was last fetched from TNB

**Note:** Negative values indicate a rebate; positive values indicate a surcharge.

## Home Assistant Integration

Once the scraper is running, use it with TNB Calculator:

```yaml
service: tnb_calculator.fetch_tariff_rates
data:
  api_url: "http://<your-server-ip>:8000/afa/simple"
```

### Monthly Automation

```yaml
automation:
  - alias: "Update TNB AFA Rate Monthly"
    trigger:
      - platform: time
        at: "00:08:00"
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"
    action:
      - service: tnb_calculator.fetch_tariff_rates
        data:
          api_url: "http://<your-server-ip>:8000/afa/simple"
```

## How It Works

1. Uses Playwright (headless Chromium) to load the TNB tariff page
2. Waits for JavaScript to render the AFA table
3. Parses the table to extract rates and periods
4. Returns the rate matching the current month

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

- **Base Image:** `mcr.microsoft.com/playwright/python:v1.40.0-focal`
- **Framework:** FastAPI + Uvicorn
- **Browser:** Chromium (headless)
- **Port:** 8001 (mapped from 8000 in container - exposed on host port 8001 for external access)

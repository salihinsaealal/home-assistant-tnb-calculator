# Session Memory - TNB Calculator

> **Use this file as context/prompt when starting a new AI coding session.**
> Copy-paste the relevant sections or feed the entire file as initial context.

---

## Project Overview

- **Repo**: `home-assistant-tnb-calculator`
- **Remote**: `https://github.com/salihinsaealal/home-assistant-tnb-calculator.git`
- **Type**: Home Assistant custom integration (HACS-compatible)
- **Domain**: `tnb_calculator`
- **Language**: Python (no package.json / Node.js)
- **License**: MIT
- **Owner**: @salihinsaealal

### What It Does

Calculates TNB (Tenaga Nasional Berhad) electricity costs for Malaysian users. Supports Time of Use (ToU) and non-ToU tariffs, NEM solar billing, AFA optimization, daily/monthly tracking, cost predictions, and holiday-aware peak/off-peak splitting.

---

## Current State (as of 2026-07-14)

| Field | Value |
|---|---|
| **Current integration version** | `4.5.0` |
| **Current scraper version** | `3.1.0` |
| **Latest git tag** | `v4.4.6` |
| **Branch** | `master` |
| **Working tree** | All v4.4.9 + v4.5.0 + scraper v3.1.0 changes pending commit |

### What Was Done Previous Session (Two Releases)

#### v4.4.9 — Core Spike Detection Overhaul
... (see previous session notes)

#### v4.5.0 — UX Improvements
... (see previous session notes)

### What Was Done This Session (Scraper v3.1.0 Overhaul)

Complete rewrite of `tnb-afa-scraper/` to fix wrong AFA rate scraping:

1. **Dual-strategy scraping** (Option C):
   - **Primary**: Direct `rates.js` HTTP fetch — no Playwright, instant (< 1s)
   - **Fallback**: Playwright headless browser (if `rates.js` fails)
   - **Safety net**: Keeps previous cache if new scrape fails validation
2. **Removed `abs()` bug** — scraper now passes `rates.js` value AS-IS (signed). Negative=rebate, positive=surcharge. Sign matches HA integration's convention exactly
3. **Online authoritative data source**: Parses `FUEL_BY_MONTH` from `https://www.mytnb.com.my/tariff/js/rates.js` — the exact JS object powering TNB's own calculator
4. **Stricter validation**: Requires ≥3 rates, valid range (-2 to +2 RM/kWh), and current/prev month coverage
5. **Daily schedule**: Scrapes every day at 6am (was monthly). 24h cache TTL
6. **Non-blocking startup**: Server starts immediately, cache loads in background
7. **Tariff extraction from `rates.js`**: Parses `DOMESTIC`, `DOMESTIC_TOU` constants for base tariff rates (generation, capacity, network, retailing, ICT tiers)
8. **Version bump**: `3.0.0` → `3.1.0`
9. **`DEFAULT_AFA_RATE` updated**: `const.py` changed from `-0.0499` (Jan 2026) to `+0.0359` (Jul 2026 surcharge)

### What Still Needs To Be Done (next session)

- [ ] **Integration releases**: `git add`, commit, tag & push v4.4.9 and v4.5.0
- [ ] **Scraper release**: Tag & push scraper v3.1.0
- [ ] Rebuild & deploy scraper Docker container on server
- [ ] Verify HA picks up new AFA rate correctly via scraper API

---

## Version Bump Checklist

When bumping the version for a new release, update these **4 locations**:

| # | File | Field | Example |
|---|---|---|---|
| 1 | `custom_components/tnb_calculator/manifest.json` | `"version"` (line 12) | `"version": "X.Y.Z"` |
| 2 | `custom_components/tnb_calculator/const.py` | `CONF_VERSION` (line 30) | `CONF_VERSION = "X.Y.Z"` |
| 3 | `custom_components/tnb_calculator/sensor.py` | `sw_version=` (line ~106) | `sw_version="X.Y.Z"` |
| 4 | `custom_components/tnb_calculator/sensor.py` | `"sw_version":` (line ~3302) | `"sw_version": "X.Y.Z"` |

Then update documentation:
- `CHANGELOG.md` - Add new version entry at top
- `README.md` - "What's New" section + Version History list
- `info.md` - "What's New" section (shown in HACS store)
- `RELEASE_NOTES_X.Y.Z.md` - Create new release notes file
- `TODO.md` - Update completed items if applicable

---

## Key File Map

```
custom_components/tnb_calculator/
├── __init__.py        # Entry setup, services, webhook registration
├── config_flow.py     # UI config flow + options flow (VERSION = 1 schema)
├── const.py           # Constants, CONF_VERSION, sensor type definitions
├── manifest.json      # HA integration manifest (version here)
├── sensor.py          # Main coordinator + all sensor entities (~3632 lines)
├── button.py          # Accept Spike Reading button entity (v4.4.9+)
├── services.yaml      # Service definitions for HA UI
├── strings.json       # UI translation strings
├── switch.py          # Auto-fetch tariffs switch entity
└── text.py            # AFA API URL text entity

dashboards/            # Pre-built HA dashboard YAML files
blueprints/            # HA automation blueprints
tnb-afa-scraper/       # External FastAPI AFA scraper (separate versioning: 3.1.0)
                       # v3.1.0+: Dual-strategy (rates.js direct + Playwright fallback)
```

### Documentation Files

| File | Purpose |
|---|---|
| `README.md` | Main repo documentation, "What's New", features, installation, usage |
| `CHANGELOG.md` | Full changelog (all versions) |
| `info.md` | HACS store description card |
| `TODO.md` | Delivery roadmap and backlog |
| `troubleshooting.md` | User-facing troubleshooting guide |
| `examples.md` | Usage examples |
| `FIX_SPIKE_DETECTION.md` | User guide for fixing spike detection issues |
| `SPIKE_ROOT_CAUSE.md` | Technical root cause analysis of spike detection bugs |
| `RELEASE_NOTES_X.Y.Z.md` | Per-release detailed notes |
| `dashboards/README.md` | Dashboard setup instructions |
| `tnb-afa-scraper/README.md` | AFA scraper setup |

---

## Git & Release Workflow

1. Make code changes on `master` branch
2. Bump version in 4 code locations (see checklist above)
3. Update all docs (CHANGELOG, README, info.md, release notes)
4. Commit and push
5. Create annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z: description"`
6. Push tags: `git push origin master --tags`
7. Create GitHub Release from the tag (use RELEASE_NOTES content as body)
8. For pre-releases: mark GitHub release as "Pre-release" (HACS detects this)
9. HACS auto-detects new version from `manifest.json` + GitHub release

### Branch Strategy

- `master` - Main/stable branch
- `beta` - Beta testing branch (used for pre-releases)

---

## Architecture Notes

- **Coordinator pattern**: `TNBDataCoordinator` (in `sensor.py`) extends `DataUpdateCoordinator`
  - NOTE: Two coordinator instances exist — one in `__init__.py` (used by services/switch/text/button), one in `sensor.py::async_setup_entry` (used by sensors). Button now triggers integration reload to sync them.
- **Storage**: Persistent JSON storage keyed by import entity name (survives delete/re-add)
- **Spike detection**: 3-layer recovery in `_compute_delta()`:
  - Layer 1: Time-aware threshold (scales with elapsed offline minutes)
  - Layer 2: Auto-recovery after 3 consecutive rejections
  - Layer 3: Spike-blocked flag + user override via button entity
- **Button entity**: `button.py` — `TNBAcceptSpikeButton` (DIAGNOSTIC, available only when spike is blocked)
- **Spike indicator**: `sensor.tnb_calculator_spike_detected` shows `on`/`off`
- **Persistent notification**: Fires on first spike detection, auto-dismisses on resolution
- **Tariffs**: Hardcoded defaults with optional API override via scraper
- **Scraper v3.1.0**: Dual-strategy — primary fetches `rates.js` directly (authoritative JS source), fallback uses Playwright. Passes signed AFA values (neg=rebate, pos=surcharge). Daily refresh at 6am. Non-blocking startup.
- **Holiday detection**: Calendarific API with local caching (daily refresh, yearly fetch)
- **Peak hours**: 2PM-10PM weekdays (TNB ToU schedule)
- **Billing tiers**: 600 kWh and 1500 kWh thresholds
- **Config flow schema version**: 1 (in `config_flow.py`)
- **Storage schema version**: 1 (in `sensor.py`)

---

## Recent Release History

| Version | Date | Highlights |
|---|---|---|---|
| v4.5.0 | 2026-07-14 | Spike indicator sensor, HA notification alert, instant fix button, smart button availability |
| v4.4.9 | 2026-07-14 | Smarter spike detection — time-aware recovery, auto-reset, Accept Spike Reading button |
| scraper v3.1.0 | 2026-07-14 | rates.js direct fetch (primary), removed abs() sign bug, daily schedule, non-blocking startup |
| v4.4.8 | 2026-05-17 | Fix baseline corruption during router reconnects; preserve last known baseline |
| v4.4.7 | 2026-04-10 | Fix ideal_import_kwh_tou/non_tou unavailable on fallback (PR #4) |
| v4.4.6 | 2026-02-28 | KWTBB/Service Tax outside NEM floor, today cost fix for solar |
| v4.4.5 | 2026-02-28 | NEM credits capped, excess carry-forward, monthly bill history |
| v4.4.4 | 2025-12-18 | Delta-based daily peak/off-peak tracking |
| v4.4.3 | 2025-12-18 | Separate ToU/non-ToU recommendations, stay_put zone |
| v4.4.2 | 2025-12-17 | Marginal rate AFA optimization |
| v4.4.1 | 2025-12-13 | AFA optimization sensors + dashboard |

---

## Prompt Template for Next Session

```
I'm working on the TNB Calculator Home Assistant integration.
Repo: /Users/salihin/Local Repositories/home-assistant-tnb-calculator
Current version: 4.5.0

Read SESSION_MEMORY.md for full project context.

Task: [describe what you need to do]
```

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

## Current State (as of 2026-04-10)

| Field | Value |
|---|---|
| **Current version** | `4.4.7` |
| **Latest git tag** | `v4.4.6` (tag for v4.4.7 not yet created) |
| **Branch** | `master` |
| **Last PR merged** | PR #4 from @zubir2k (Add TOU and non-TOU ideal import kWh values) |
| **Working tree** | Docs/version bump changes pending commit |

### What Was Done This Session

1. Bumped version `4.4.6` -> `4.4.7` in all 4 code locations
2. Updated `CHANGELOG.md` with v4.4.7 entry
3. Updated `README.md` "What's New" section and Version History
4. Updated `info.md` with v4.4.7 and v4.4.5 summaries
5. Created `RELEASE_NOTES_4.4.7.md`
6. Updated `TODO.md` completed items and release cadence

### What Still Needs To Be Done (next session)

- [ ] `git add` and `git commit` all changes (if not done yet)
- [ ] Create git tag `v4.4.7`
- [ ] Push to remote: `git push origin master --tags`
- [ ] Create GitHub Release for `v4.4.7` (use `RELEASE_NOTES_4.4.7.md` as body)
- [ ] Verify HACS picks up new version

---

## Version Bump Checklist

When bumping the version for a new release, update these **4 locations**:

| # | File | Field | Example |
|---|---|---|---|
| 1 | `custom_components/tnb_calculator/manifest.json` | `"version"` (line 12) | `"version": "X.Y.Z"` |
| 2 | `custom_components/tnb_calculator/const.py` | `CONF_VERSION` (line 24) | `CONF_VERSION = "X.Y.Z"` |
| 3 | `custom_components/tnb_calculator/sensor.py` | `sw_version=` (line ~104) | `sw_version="X.Y.Z"` |
| 4 | `custom_components/tnb_calculator/sensor.py` | `"sw_version":` (line ~3067) | `"sw_version": "X.Y.Z"` |

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
├── sensor.py          # Main coordinator + all sensor entities (~3389 lines)
├── services.yaml      # Service definitions for HA UI
├── strings.json       # UI translation strings
├── switch.py          # Auto-fetch tariffs switch entity
└── text.py            # AFA API URL text entity

dashboards/            # Pre-built HA dashboard YAML files
blueprints/            # HA automation blueprints
tnb-afa-scraper/       # External FastAPI+Playwright AFA scraper (separate versioning: 3.0.0)
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
| `RELEASE_NOTES_X.Y.Z.md` | Per-release detailed notes |
| `dashboards/README.md` | Dashboard setup instructions |
| `tnb-afa-scraper/README.md` | AFA scraper setup |

---

## Git & Release Workflow

1. Make code changes on `master` branch
2. Bump version in 4 code locations (see checklist above)
3. Update all docs (CHANGELOG, README, info.md, release notes)
4. Commit and push
5. Create annotated tag: `git tag -a v4.4.7 -m "v4.4.7: AFA optimization sensor fix"`
6. Push tags: `git push origin master --tags`
7. Create GitHub Release from the tag (use RELEASE_NOTES content as body)
8. HACS auto-detects new version from `manifest.json` + GitHub release

### Branch Strategy

- `master` - Main/stable branch
- `beta` - Beta testing branch (used for `v4.4.0b1`, `v4.4.0b2` style pre-releases)

---

## Architecture Notes

- **Coordinator pattern**: `TNBDataCoordinator` (in `sensor.py`) extends `DataUpdateCoordinator`
- **Storage**: Persistent JSON storage keyed by import entity name (survives delete/re-add)
- **Tariffs**: Hardcoded defaults with optional API override via scraper
- **Holiday detection**: Calendarific API with local caching (daily refresh, yearly fetch)
- **Peak hours**: 2PM-10PM weekdays (TNB ToU schedule)
- **Billing tiers**: 600 kWh and 1500 kWh thresholds
- **Config flow schema version**: 1 (in `config_flow.py`)
- **Storage schema version**: 1 (in `sensor.py`)

---

## Recent Release History

| Version | Date | Highlights |
|---|---|---|
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
Current version: 4.4.7

Read SESSION_MEMORY.md for full project context.

Task: [describe what you need to do]
```

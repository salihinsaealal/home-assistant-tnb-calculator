"""
TNB AFA Rate Scraper API

Caching Strategy:
- Scrapes TNB website on startup and twice monthly (1st & 25th at 6am)
- Caches results to JSON file for instant API responses
- /afa/simple returns cached data with last_scraped timestamp
- /afa/refresh forces a re-scrape

GET /           -> health check
GET /afa/simple -> { "afa_rate": <RM/kWh>, "effective_date": "...", "last_scraped": "..." }
GET /afa/refresh -> force re-scrape and return new data
GET /afa/debug  -> debug info (triggers live scrape)
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache configuration
CACHE_FILE = Path("/app/data/afa_cache.json")
AFA_URL = "https://www.mytnb.com.my/tariff/index.html#afa"

# Global cache (in-memory, backed by file)
_cache: Dict[str, Any] = {}
_scheduler_task: Optional[asyncio.Task] = None


def _load_cache() -> Dict[str, Any]:
    """Load cache from file if exists."""
    global _cache
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                _cache = json.load(f)
                logger.info("Loaded cache from %s (last_scraped: %s)", 
                           CACHE_FILE, _cache.get("last_scraped"))
        except Exception as e:
            logger.error("Failed to load cache: %s", e)
            _cache = {}
    return _cache


def _save_cache(data: Dict[str, Any]) -> None:
    """Save cache to file."""
    global _cache
    _cache = data
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved cache to %s", CACHE_FILE)
    except Exception as e:
        logger.error("Failed to save cache: %s", e)


async def _scheduled_scraper():
    """Background task that scrapes on 1st and 25th of each month at 6am."""
    while True:
        now = datetime.now()
        # Check if today is 1st or 25th and it's around 6am
        if now.day in (1, 25) and now.hour == 6:
            logger.info("Scheduled scrape triggered (day=%d)", now.day)
            try:
                await _do_scrape_and_cache()
            except Exception as e:
                logger.error("Scheduled scrape failed: %s", e)
        
        # Sleep for 1 hour before checking again
        await asyncio.sleep(3600)


async def _do_scrape_and_cache() -> Dict[str, Any]:
    """Perform scrape and update cache."""
    logger.info("Starting scrape...")
    body_text, debug_log = await _scrape_raw()
    all_rates = _extract_rates(body_text)
    tariffs = _extract_tariffs(body_text)
    
    if not all_rates:
        logger.error("Scrape found no rates!")
        raise HTTPException(status_code=500, detail="Could not find any AFA rates in page")
    
    now = datetime.now()
    
    # Pick current month's rate
    current = _select_current_rate(all_rates, now)
    
    cache_data = {
        "last_scraped": now.isoformat(),
        "all_rates": all_rates,
        "tariffs": tariffs,
        "current_rate": {
            # Store absolute value (positive) for Home Assistant compatibility
            # TNB returns negative for rebates, but HA integration expects positive
            "afa_rate": abs(current["rate_rm"]),
            "afa_rate_raw": current["rate_rm"],  # Keep original for reference
            "effective_date": f"{current['year']:04d}-{current['start_month']:02d}-01",
            "period": current["period"],
            "rate_sen": current["rate_sen"],
        },
    }
    
    _save_cache(cache_data)
    logger.info("Scrape complete. Current rate: %.4f RM/kWh for %s", 
               current["rate_rm"], current["period"])
    
    return cache_data


def _select_current_rate(all_rates: List[Dict], now: datetime) -> Dict[str, Any]:
    """Select the rate that covers the current month."""
    for item in all_rates:
        if item["year"] == now.year and item["start_month"] <= now.month <= item["end_month"]:
            return item
    
    # Fallback to most recent
    return sorted(all_rates, key=lambda x: (x["year"], x["end_month"]), reverse=True)[0]


def _extract_tariffs(text: str) -> Dict[str, Any]:
    """Extract all tariff components from the TNB page text.

    Parses:
    1. Non-ToU rates (Caj Tenaga without puncak/luar puncak)
    2. ToU rates (Caj Tenaga with puncak/luar puncak)
    3. Capacity and Network (shared across all)
    4. Retailing charge (Caj Peruncitan)
    5. ICT tiers (Insentif Cekap Tenaga)

    Returns a comprehensive dict in RM/kWh (or RM for fixed charges):
    {
      "non_tou": {
        "tier1": {"generation": 0.2703, "capacity": 0.0455, "network": 0.1285},
        "tier2": {"generation": 0.3703, ...},
        "threshold_kwh": 600
      },
      "tou": {
        "tier1": {"generation_peak": 0.2852, "generation_offpeak": 0.2443, ...},
        "tier2": {"generation_peak": 0.3852, "generation_offpeak": 0.3443, ...},
        "threshold_kwh": 1500
      },
      "shared": {
        "capacity": 0.0455,
        "network": 0.1285,
        "retailing": 10.00
      },
      "ict_tiers": [
        {"min_kwh": 1, "max_kwh": 200, "rate": -0.25},
        ...
      ]
    }
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    def sen_to_rm(val: float) -> float:
        return round(val / 100.0, 6)

    def parse_last_number(line: str) -> Optional[float]:
        """Extract the last numeric value from a line."""
        # Handle tabs or multiple spaces as delimiters
        parts = [p.strip() for p in re.split(r'[\t]+', line) if p.strip()]
        if not parts:
            return None
        try:
            # Try to parse the last part as a number
            return float(parts[-1].replace(',', ''))
        except ValueError:
            return None

    # Storage for parsed values
    non_tou_gen: List[float] = []  # Non-ToU generation rates
    tou_peak: List[float] = []     # ToU peak rates
    tou_offpeak: List[float] = []  # ToU off-peak rates
    capacity_vals: List[float] = []
    network_vals: List[float] = []
    retailing_vals: List[float] = []
    ict_tiers: List[Dict[str, Any]] = []

    for line in lines:
        lower = line.lower()

        # === Non-ToU Generation ===
        # "Caj Tenaga - Untuk semua kWj" (without puncak/luar puncak)
        if "caj tenaga - untuk semua kwj" in lower and "puncak" not in lower:
            val = parse_last_number(line)
            if val is not None:
                non_tou_gen.append(val)

        # === ToU Peak ===
        # "Caj Tenaga - Untuk semua kWj semasa tempoh puncak"
        elif "caj tenaga" in lower and "tempoh puncak" in lower and "luar" not in lower:
            val = parse_last_number(line)
            if val is not None:
                tou_peak.append(val)

        # === ToU Off-Peak ===
        # "Caj Tenaga - Untuk semua kWj semasa tempoh luar puncak"
        elif "caj tenaga" in lower and "luar puncak" in lower:
            val = parse_last_number(line)
            if val is not None:
                tou_offpeak.append(val)

        # === Capacity ===
        elif "caj kapasiti - untuk semua kwj" in lower:
            val = parse_last_number(line)
            if val is not None:
                capacity_vals.append(val)

        # === Network ===
        elif "caj rangkaian - untuk semua kwj" in lower:
            val = parse_last_number(line)
            if val is not None:
                network_vals.append(val)

        # === Retailing ===
        elif "caj peruncitan" in lower and "rm/bulan" in lower:
            val = parse_last_number(line)
            if val is not None:
                retailing_vals.append(val)

        # === ICT Tiers ===
        # Pattern: "1 - 200 sen/kWj -25.0" or "901 - 1,000 sen/kWj -0.5"
        elif "sen/kwj" in lower and re.search(r'\d+\s*-\s*[\d,]+', line):
            # Check if this is an ICT tier (has negative rate or is in ICT section)
            range_match = re.search(r'(\d+)\s*-\s*([\d,]+)', line)
            rate_match = re.search(r'(-?\d+\.?\d*)\s*$', line.strip())
            if range_match and rate_match:
                min_kwh = int(range_match.group(1))
                max_kwh = int(range_match.group(2).replace(',', ''))
                rate_sen = float(rate_match.group(1))
                # ICT rates are typically negative (rebates)
                if rate_sen <= 0 or min_kwh >= 1:
                    ict_tiers.append({
                        "min_kwh": min_kwh,
                        "max_kwh": max_kwh,
                        "rate_sen": rate_sen,
                        "rate_rm": sen_to_rm(rate_sen),
                    })

    # Build result dict
    result: Dict[str, Any] = {}

    # === Non-ToU ===
    if non_tou_gen:
        non_tou_sorted = sorted(set(non_tou_gen))
        tier1_gen = non_tou_sorted[0]
        tier2_gen = non_tou_sorted[1] if len(non_tou_sorted) > 1 else tier1_gen
        result["non_tou"] = {
            "tier1": {
                "generation": sen_to_rm(tier1_gen),
            },
            "tier2": {
                "generation": sen_to_rm(tier2_gen),
            },
            "threshold_kwh": 600,  # From TNB: "600 kWj dan ke bawah"
            "note": "tier1 for ≤600 kWh, tier2 for >600 kWh",
        }

    # === ToU ===
    if tou_peak and tou_offpeak:
        peak_sorted = sorted(set(tou_peak))
        offpeak_sorted = sorted(set(tou_offpeak))
        result["tou"] = {
            "tier1": {
                "generation_peak": sen_to_rm(peak_sorted[0]),
                "generation_offpeak": sen_to_rm(offpeak_sorted[0]),
            },
            "tier2": {
                "generation_peak": sen_to_rm(peak_sorted[1]) if len(peak_sorted) > 1 else sen_to_rm(peak_sorted[0]),
                "generation_offpeak": sen_to_rm(offpeak_sorted[1]) if len(offpeak_sorted) > 1 else sen_to_rm(offpeak_sorted[0]),
            },
            "threshold_kwh": 1500,  # From integration: uses different rates above 1500
            "note": "tier1 for <1500 kWh, tier2 for ≥1500 kWh",
        }

    # === Shared rates ===
    shared: Dict[str, Any] = {}
    if capacity_vals:
        shared["capacity"] = sen_to_rm(capacity_vals[0])
    if network_vals:
        shared["network"] = sen_to_rm(network_vals[0])
    if retailing_vals:
        shared["retailing"] = retailing_vals[0]  # Already in RM
    if shared:
        result["shared"] = shared

    # === ICT Tiers ===
    if ict_tiers:
        # Sort by min_kwh and deduplicate
        seen = set()
        unique_tiers = []
        for tier in sorted(ict_tiers, key=lambda x: x["min_kwh"]):
            key = (tier["min_kwh"], tier["max_kwh"])
            if key not in seen:
                seen.add(key)
                unique_tiers.append(tier)
        result["ict_tiers"] = unique_tiers

    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global _scheduler_task
    
    # Load existing cache
    _load_cache()
    
    # If no cache or cache is old, scrape on startup
    if not _cache or "last_scraped" not in _cache:
        logger.info("No cache found, scraping on startup...")
        try:
            await _do_scrape_and_cache()
        except Exception as e:
            logger.error("Startup scrape failed: %s", e)
    
    # Start background scheduler
    _scheduler_task = asyncio.create_task(_scheduled_scraper())
    logger.info("Background scheduler started")
    
    yield
    
    # Shutdown
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("Scraper shutdown complete")


app = FastAPI(
    title="TNB AFA Rate Scraper",
    description="Scrapes myTNB tariff page for AFA rates with caching",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> Dict[str, Any]:
    """Health check with cache status."""
    return {
        "status": "ok",
        "service": "TNB AFA Rate Scraper",
        "version": "2.0.0",
        "cache_loaded": bool(_cache),
        "last_scraped": _cache.get("last_scraped"),
    }


async def _scrape_raw() -> Tuple[str, List[str]]:
    """Use Playwright to get the full page text for parsing.
    
    Returns:
        Tuple of (body_text, debug_log)
    """
    debug_log: List[str] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            debug_log.append("Navigating to page...")
            await page.goto(AFA_URL, wait_until="networkidle", timeout=40000)
            debug_log.append("Page loaded, waiting for JS...")

            # Give the page some time for JS to render
            await page.wait_for_timeout(3000)
            
            # Strategy 1: Try clicking accordion items by common patterns
            # The AFA section is typically in an accordion/card that needs clicking
            accordion_selectors = [
                # Common accordion patterns
                ".accordion-item:has-text('Mekanisme Pelarasan')",
                ".accordion-item:has-text('AFA')",
                ".card:has-text('Mekanisme Pelarasan')",
                ".card:has-text('AFA')",
                "[data-toggle='collapse']:has-text('Mekanisme')",
                "button:has-text('Mekanisme Pelarasan')",
                "a:has-text('Mekanisme Pelarasan')",
                # Try clicking any element with AFA text
                "*:has-text('Mekanisme Pelarasan Kos Bahan Api Secara Automatik')",
            ]
            
            for selector in accordion_selectors:
                try:
                    locator = page.locator(selector)
                    count = await locator.count()
                    if count > 0:
                        debug_log.append(f"Found {count} elements for: {selector}")
                        await locator.first.click()
                        await page.wait_for_timeout(1500)
                        debug_log.append(f"Clicked: {selector}")
                        break
                except Exception as e:
                    debug_log.append(f"Selector failed {selector}: {str(e)[:50]}")

            # Strategy 2: Try clicking by visible text (broader search)
            text_patterns = [
                "Mekanisme Pelarasan Kos Bahan Api Secara Automatik",
                "Mekanisme Pelarasan Kos Bahan Api",
                "Automatic Fuel Adjustment",
            ]
            
            for text in text_patterns:
                try:
                    locator = page.get_by_text(text, exact=False)
                    count = await locator.count()
                    if count > 0:
                        debug_log.append(f"Found {count} elements with text: '{text}'")
                        # Try clicking each match
                        for i in range(min(count, 3)):
                            try:
                                await locator.nth(i).click()
                                await page.wait_for_timeout(1000)
                                debug_log.append(f"Clicked text match #{i+1}")
                            except Exception:
                                pass
                except Exception as e:
                    debug_log.append(f"Text search failed '{text}': {str(e)[:50]}")
            
            # Strategy 3: Look for and click any collapsed/expandable sections
            try:
                # Click all accordion buttons/headers that might reveal content
                expandables = page.locator("[aria-expanded='false'], .collapsed, .accordion-button:not(.show)")
                count = await expandables.count()
                debug_log.append(f"Found {count} expandable elements")
                for i in range(min(count, 5)):
                    try:
                        await expandables.nth(i).click()
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass
            except Exception as e:
                debug_log.append(f"Expandables search failed: {str(e)[:50]}")

            # Wait a bit more for any animations
            await page.wait_for_timeout(2000)

            body_text = await page.inner_text("body")
            debug_log.append(f"Scraped {len(body_text)} chars of text")
            
            return body_text, debug_log
        finally:
            await browser.close()


def _parse_month_year(s: str) -> Optional[Tuple[int, int]]:
    """Parse '1 – 30 November 2025' -> (11, 2025).

    Kept for backwards compatibility, but more advanced range parsing
    is handled by _parse_period below.
    """
    months = {
        "january": 1,
        "februari": 2,
        "february": 2,
        "mac": 3,
        "march": 3,
        "april": 4,
        "mei": 5,
        "may": 5,
        "jun": 6,
        "june": 6,
        "julai": 7,
        "july": 7,
        "ogos": 8,
        "august": 8,
        "september": 9,
        "oktober": 10,
        "october": 10,
        "november": 11,
        "disember": 12,
        "december": 12,
    }
    lower = s.lower()
    year_match = re.search(r"(\d{4})", s)
    if not year_match:
        return None
    year = int(year_match.group(1))

    for name, num in months.items():
        if name in lower:
            return num, year
    return None


def _parse_period(s: str) -> Optional[Tuple[int, int, int]]:
    """Parse a period line into (start_month, end_month, year).

    Examples:
    - "1 – 30 November 2025" -> (11, 11, 2025)
    - "1 Julai – 30 September 2025" -> (7, 9, 2025)
    """
    months = {
        "january": 1,
        "februari": 2,
        "february": 2,
        "mac": 3,
        "march": 3,
        "april": 4,
        "mei": 5,
        "may": 5,
        "jun": 6,
        "june": 6,
        "julai": 7,
        "july": 7,
        "ogos": 8,
        "august": 8,
        "september": 9,
        "oktober": 10,
        "october": 10,
        "november": 11,
        "disember": 12,
        "december": 12,
    }

    lower = s.lower()
    year_match = re.search(r"(\d{4})", s)
    if not year_match:
        return None
    year = int(year_match.group(1))

    # Find all month name occurrences with positions
    positions: List[Tuple[int, int]] = []
    for name, num in months.items():
        for match in re.finditer(name, lower):
            positions.append((match.start(), num))

    if not positions:
        return None

    positions.sort(key=lambda x: x[0])

    # Single month mentioned -> start=end
    if len(positions) == 1:
        month = positions[0][1]
        return month, month, year

    # Multiple months -> treat first as start, last as end
    start_month = positions[0][1]
    end_month = positions[-1][1]
    return start_month, end_month, year


def _extract_rates(text: str) -> List[Dict[str, Any]]:
    """
    Extract rates & periods from body text.

    Looks for lines containing both a month range and a 'sen / kWj' style value.
    Handles tab-separated columns (e.g., Nov\tDec with rates -8.91\t-6.42).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    results: List[Dict[str, Any]] = []

    # Pass 1: only consider lines in the main "Kadar Mekanisme..." table,
    # and ignore the "Unjuran 3-Bulan" forecast table below it.
    in_current_section = False

    for i, line in enumerate(lines):
        lower_line = line.lower()

        if "kadar mekanisme pelarasan kos bahan api secara automatik" in lower_line:
            in_current_section = True
            continue

        if "unjuran 3-bulan" in lower_line:
            in_current_section = False
            continue

        if not in_current_section:
            continue

        # Look for 'sen / kWj' in the line
        if "sen" in lower_line and "kw" in lower_line:
            # Try to pick the previous line as the period
            period_line = lines[i - 1] if i > 0 else ""
            
            # Handle tab-separated columns (multiple periods & rates)
            period_cols = [p.strip() for p in period_line.split("\t") if p.strip()]
            rate_cols = [r.strip() for r in line.split("\t") if r.strip()]
            
            # If we have matching columns, parse each separately
            if len(period_cols) > 1 and len(rate_cols) == len(period_cols):
                for period_col, rate_col in zip(period_cols, rate_cols):
                    period_info = _parse_period(period_col)
                    rate_match = re.search(r"(-?\d+\.?\d*)", rate_col)
                    if period_info and rate_match:
                        start_month, end_month, year = period_info
                        rate_sen = float(rate_match.group(1))
                        results.append(
                            {
                                "period": period_col,
                                "rate_sen": rate_sen,
                                "rate_rm": rate_sen / 100.0,
                                "start_month": start_month,
                                "end_month": end_month,
                                "year": year,
                            }
                        )
            else:
                # Fallback: parse as single line
                period_info = _parse_period(period_line)
                rate_match = re.search(r"(-?\d+\.?\d*)", line)
                if period_info and rate_match:
                    start_month, end_month, year = period_info
                    rate_sen = float(rate_match.group(1))
                    results.append(
                        {
                            "period": period_line,
                            "rate_sen": rate_sen,
                            "rate_rm": rate_sen / 100.0,
                            "start_month": start_month,
                            "end_month": end_month,
                            "year": year,
                        }
                    )

    # Pass 2: if we found nothing (maybe headings changed), fall back to
    # scanning the whole page like before.
    if not results:
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if "sen" in lower_line and "kw" in lower_line:
                period_line = lines[i - 1] if i > 0 else ""
                
                # Handle tab-separated columns
                period_cols = [p.strip() for p in period_line.split("\t") if p.strip()]
                rate_cols = [r.strip() for r in line.split("\t") if r.strip()]
                
                if len(period_cols) > 1 and len(rate_cols) == len(period_cols):
                    for period_col, rate_col in zip(period_cols, rate_cols):
                        period_info = _parse_period(period_col)
                        rate_match = re.search(r"(-?\d+\.?\d*)", rate_col)
                        if period_info and rate_match:
                            start_month, end_month, year = period_info
                            rate_sen = float(rate_match.group(1))
                            results.append(
                                {
                                    "period": period_col,
                                    "rate_sen": rate_sen,
                                    "rate_rm": rate_sen / 100.0,
                                    "start_month": start_month,
                                    "end_month": end_month,
                                    "year": year,
                                }
                            )
                else:
                    period_info = _parse_period(period_line)
                    rate_match = re.search(r"(-?\d+\.?\d*)", line)
                    if period_info and rate_match:
                        start_month, end_month, year = period_info
                        rate_sen = float(rate_match.group(1))
                        results.append(
                            {
                                "period": period_line,
                                "rate_sen": rate_sen,
                                "rate_rm": rate_sen / 100.0,
                                "start_month": start_month,
                                "end_month": end_month,
                                "year": year,
                            }
                        )
    return results


@app.get("/afa/simple")
async def get_afa_simple() -> Dict[str, Any]:
    """
    Return the AFA rate for the *current* month from cache (instant response).

    Response:
    {
      "afa_rate": -0.0891,
      "effective_date": "2025-11-01",
      "last_scraped": "2025-11-28T09:00:00"
    }
    """
    if not _cache or "current_rate" not in _cache:
        # No cache - need to scrape first
        logger.warning("Cache miss on /afa/simple, triggering scrape...")
        await _do_scrape_and_cache()
    
    current = _cache["current_rate"]
    
    return {
        "afa_rate": current["afa_rate"],  # Positive value for HA
        "afa_rate_raw": current.get("afa_rate_raw", current["afa_rate"]),  # Original (may be negative)
        "effective_date": current["effective_date"],
        "last_scraped": _cache.get("last_scraped"),
    }


@app.get("/refresh")
async def refresh_all() -> Dict[str, Any]:
    """
    Force a re-scrape of TNB website and update cache.
    Use this if you need fresh data immediately.
    
    Returns summary of refreshed data.
    """
    logger.info("Manual refresh triggered via /refresh")
    cache_data = await _do_scrape_and_cache()
    
    return {
        "status": "refreshed",
        "afa_rate": cache_data["current_rate"]["afa_rate"],  # Positive
        "afa_rate_raw": cache_data["current_rate"].get("afa_rate_raw"),  # Original
        "effective_date": cache_data["current_rate"]["effective_date"],
        "last_scraped": cache_data["last_scraped"],
        "all_rates_count": len(cache_data["all_rates"]),
    }


@app.get("/afa/all")
async def get_all_rates() -> Dict[str, Any]:
    """
    Return all cached AFA rates (current + upcoming months).
    """
    if not _cache or "all_rates" not in _cache:
        logger.warning("Cache miss on /afa/all, triggering scrape...")
        await _do_scrape_and_cache()
    
    return {
        "last_scraped": _cache.get("last_scraped"),
        "current_rate": _cache.get("current_rate"),
        "all_rates": _cache.get("all_rates", []),
    }


@app.get("/complete")
async def get_complete_data() -> Dict[str, Any]:
    """
    Return complete cached tariff data (AFA + base rates + future ToU/ICT).
    
    This endpoint provides:
    - last_scraped: When data was fetched from TNB
    - current_rate: The AFA rate applicable for the current month
    - all_rates: All AFA rates with both raw and absolute values
    - tariffs: Base tariff rates (generation/capacity/network)
    - metadata: Additional info about the data
    
    All AFA rates include:
    - rate_rm: Original value (negative = rebate)
    - rate_rm_abs: Absolute value (always positive, for HA compatibility)
    """
    if not _cache or "all_rates" not in _cache:
        logger.warning("Cache miss on /complete, triggering scrape...")
        await _do_scrape_and_cache()
    
    # Enrich all_rates with absolute values
    enriched_rates = []
    for rate in _cache.get("all_rates", []):
        enriched = rate.copy()
        enriched["rate_rm_abs"] = abs(rate.get("rate_rm", 0))
        enriched_rates.append(enriched)
    
    return {
        "last_scraped": _cache.get("last_scraped"),
        "current_rate": _cache.get("current_rate"),
        "all_rates": enriched_rates,
        "tariffs": _cache.get("tariffs", {}),
        "metadata": {
            "source": "https://www.mytnb.com.my/tariff/index.html#afa",
            "rates_count": len(enriched_rates),
            "note": "rate_rm is original (negative=rebate), rate_rm_abs is always positive",
        },
    }


@app.get("/debug")
async def get_debug_data() -> Dict[str, Any]:
    """Debug endpoint - performs LIVE scrape (slow) to see raw data.
    
    Use this to study the page structure for parsing improvements.
    """
    now = datetime.now()
    body_text, debug_log = await _scrape_raw()
    all_rates = _extract_rates(body_text)
    tariffs = _extract_tariffs(body_text)
    
    # Find lines containing tariff-related keywords
    tariff_lines = []
    for ln in body_text.splitlines():
        lower = ln.lower().strip()
        if any(kw in lower for kw in ["sen/kwj", "rm/kwj", "caj ", "kadar", "puncak", "luar puncak", "blok", "insentif"]):
            tariff_lines.append(ln.strip())
    
    return {
        "current_date": now.isoformat(),
        "debug_log": debug_log,
        "afa_rates_found": all_rates,
        "tariffs_found": tariffs,
        "tariff_lines": tariff_lines[:100],  # More lines for study
        "body_text_length": len(body_text),
        "body_text_full": body_text,  # Full text for thorough study
    }

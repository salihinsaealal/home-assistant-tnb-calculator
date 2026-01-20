"""
TNB AFA Rate Scraper API v3.0

Smart Caching Strategy:
- Scrapes TNB website on startup (if no cache)
- Monthly schedule: 1st of month at 6am
- Smart skipping: Skips scrape if cache has current + next 2 months
- Auto-retry: Retries every 6 hours on failure (max 4 attempts)
- Data validation: Validates scraped data before caching
- Keeps old cache if new scrape fails validation

Endpoints:
GET /           -> health check
GET /health     -> detailed monitoring status
GET /afa/simple -> cached current month rate
GET /complete   -> all rates + tariffs (cached)
GET /refresh    -> force re-scrape
GET /debug      -> debug info (triggers live scrape)
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

# Retry state for smart scheduling
_retry_state: Dict[str, Any] = {
    "last_attempt": None,
    "consecutive_failures": 0,
    "last_success": None,
    "last_scrape_duration": 0.0,
    "rates_found_count": 0,
}


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


def _validate_rates(all_rates: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Validate scraped AFA rates.
    
    Returns:
        Tuple of (is_valid, reason)
    """
    if not all_rates:
        return False, "No rates found"
    
    # Check if current month rate exists
    now = datetime.now()
    current_month_rates = [
        r for r in all_rates 
        if r["year"] == now.year and r["start_month"] == now.month
    ]
    
    if not current_month_rates:
        # Check if we have previous month (might be published late)
        logger.warning(f"Current month ({now.year}-{now.month:02d}) rate not found in scraped data")
        # This is a warning, not a failure - TNB might publish late on 1st
    
    # Check if we have at least 1 rate
    if len(all_rates) < 1:
        return False, "Less than 1 rate found"
    
    logger.info(f"Validation passed: {len(all_rates)} rates found")
    return True, "OK"


def _check_need_scrape() -> Tuple[bool, str]:
    """
    Check if we need to scrape based on cache status.
    
    Returns:
        Tuple of (should_scrape, reason)
    """
    now = datetime.now()
    
    # No cache at all
    if not _cache:
        return True, "No cache exists"
    
    # Missing current month rate (emergency)
    if "all_rates" in _cache:
        current_month_rates = [
            r for r in _cache["all_rates"]
            if r["year"] == now.year and r["start_month"] == now.month
        ]
        if not current_month_rates:
            return True, "Missing current month rate"
    
    # Check if we have sufficient future data (current + next 2 months)
    if "all_rates" in _cache:
        future_months = set()
        for r in _cache["all_rates"]:
            rate_date = datetime(r["year"], r["start_month"], 1)
            if rate_date >= now:
                future_months.add((r["year"], r["start_month"]))
        
        # If we have 3+ future months, we're good
        if len(future_months) >= 3:
            logger.info(f"Cache has {len(future_months)} future months, skipping scrape")
            return False, f"Sufficient data ({len(future_months)} future months)"
    
    # Cache is too old (backup safety - 30 days)
    if "last_scraped" in _cache:
        try:
            last_scraped = datetime.fromisoformat(_cache["last_scraped"])
            days_old = (now - last_scraped).days
            if days_old > 30:
                return True, f"Cache older than 30 days ({days_old} days)"
        except Exception:
            return True, "Invalid last_scraped timestamp"
    
    return False, "Cache is sufficient"


async def _scheduled_scraper():
    """
    Smart background scheduler:
    - Scrape on 1st of month at 6am
    - Retry every 6 hours if failed (max 4 attempts = 24h)
    - Skip if we have current + next 2 months in cache
    - Emergency scrape if current month is missing
    """
    global _retry_state
    
    while True:
        now = datetime.now()
        
        # Check if we need to scrape
        should_scrape = False
        reason = ""
        
        # Reason 1: It's the 1st of the month at 6am (primary schedule)
        if now.day == 1 and now.hour == 6:
            # Check if we actually need to scrape (might have sufficient data)
            need_scrape, check_reason = _check_need_scrape()
            if need_scrape:
                should_scrape = True
                reason = f"Monthly scheduled scrape: {check_reason}"
            else:
                logger.info(f"Skipping monthly scrape: {check_reason}")
        
        # Reason 2: We have pending retries (failed scrape within 24h)
        elif _retry_state["consecutive_failures"] > 0:
            last_attempt = _retry_state.get("last_attempt")
            if last_attempt:
                hours_since = (now - last_attempt).total_seconds() / 3600
                if hours_since >= 6 and _retry_state["consecutive_failures"] < 4:
                    should_scrape = True
                    reason = f"Retry attempt {_retry_state['consecutive_failures'] + 1}/4 (last attempt: {hours_since:.1f}h ago)"
                elif _retry_state["consecutive_failures"] >= 4:
                    # Max retries reached, reset and wait for next monthly schedule
                    logger.warning("Max retries (4) reached. Will retry on next monthly schedule.")
                    _retry_state["consecutive_failures"] = 0
        
        # Reason 3: Missing current month rate (emergency scrape)
        else:
            need_scrape, check_reason = _check_need_scrape()
            if need_scrape and "Missing current month" in check_reason:
                should_scrape = True
                reason = f"Emergency: {check_reason}"
        
        # Perform scrape if needed
        if should_scrape:
            logger.info(f"🔄 Scrape triggered: {reason}")
            _retry_state["last_attempt"] = now
            
            try:
                await _do_scrape_and_cache()
            except Exception as e:
                logger.error(f"Scrape failed: {e}")
        
        # Sleep for 1 hour before checking again
        await asyncio.sleep(3600)


async def _do_scrape_and_cache() -> Dict[str, Any]:
    """Perform scrape and update cache with validation."""
    global _retry_state
    
    logger.info("Starting scrape...")
    scrape_start = datetime.now()
    
    try:
        body_text, debug_log = await _scrape_raw()
        all_rates = _extract_rates(body_text)
        tariffs = _extract_tariffs(body_text)
        
        # Measure scrape duration
        scrape_duration = (datetime.now() - scrape_start).total_seconds()
        _retry_state["last_scrape_duration"] = scrape_duration
        _retry_state["rates_found_count"] = len(all_rates)
        
        # Validate the scraped data
        is_valid, validation_msg = _validate_rates(all_rates)
        
        if not is_valid:
            logger.error(f"Scrape validation failed: {validation_msg}")
            _retry_state["consecutive_failures"] += 1
            
            # Keep old cache if validation fails
            if _cache:
                logger.warning("Keeping old cache due to validation failure")
                return _cache
            else:
                raise HTTPException(status_code=500, detail=f"Scrape validation failed: {validation_msg}")
        
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
        
        # Update success metrics
        _retry_state["consecutive_failures"] = 0
        _retry_state["last_success"] = now
        
        logger.info("Scrape complete in %.2fs. Found %d rates. Current rate: %.4f RM/kWh for %s", 
                   scrape_duration, len(all_rates), cache_data["current_rate"]["afa_rate"],
                   cache_data["current_rate"]["period"])
        
        return cache_data
        
    except Exception as e:
        scrape_duration = (datetime.now() - scrape_start).total_seconds()
        _retry_state["last_scrape_duration"] = scrape_duration
        _retry_state["consecutive_failures"] += 1
        logger.error(f"Scrape failed after {scrape_duration:.2fs}: {e}")
        
        # Keep old cache if scrape fails
        if _cache:
            logger.warning("Keeping old cache due to scrape failure")
            return _cache
        else:
            raise


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
    description="Scrapes myTNB tariff page for AFA rates with smart caching and validation",
    version="3.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> Dict[str, Any]:
    """Health check with cache status."""
    return {
        "status": "ok",
        "service": "TNB AFA Rate Scraper",
        "version": "3.0.0",
        "cache_loaded": bool(_cache),
        "last_scraped": _cache.get("last_scraped"),
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Detailed health status for monitoring.
    
    Returns comprehensive status including:
    - Current month rate availability
    - Future months in cache
    - Scrape metrics
    - Retry state
    """
    now = datetime.now()
    
    # Check current month rate
    current_month_exists = False
    future_months_count = 0
    current_month_rate = None
    
    if _cache and "all_rates" in _cache:
        for r in _cache["all_rates"]:
            if r["year"] == now.year and r["start_month"] == now.month:
                current_month_exists = True
                current_month_rate = r["rate_sen"]
            
            rate_date = datetime(r["year"], r["start_month"], 1)
            if rate_date >= now:
                future_months_count += 1
    
    # Calculate time since last scrape
    last_scraped_str = _cache.get("last_scraped") if _cache else None
    hours_since_scrape = None
    if last_scraped_str:
        try:
            last_scraped = datetime.fromisoformat(last_scraped_str)
            hours_since_scrape = (now - last_scraped).total_seconds() / 3600
        except Exception:
            pass
    
    # Calculate time since last success
    hours_since_success = None
    if _retry_state.get("last_success"):
        hours_since_success = (now - _retry_state["last_success"]).total_seconds() / 3600
    
    # Determine overall health status
    if not current_month_exists:
        status = "critical"
        message = "Missing current month rate"
    elif _retry_state["consecutive_failures"] >= 3:
        status = "warning"
        message = f"{_retry_state['consecutive_failures']} consecutive scrape failures"
    elif future_months_count < 2:
        status = "warning"
        message = f"Only {future_months_count} future months in cache"
    else:
        status = "healthy"
        message = "All systems operational"
    
    return {
        "status": status,
        "message": message,
        "current_month": {
            "exists": current_month_exists,
            "rate_sen": current_month_rate,
            "year": now.year,
            "month": now.month,
        },
        "cache": {
            "loaded": bool(_cache),
            "total_rates": len(_cache.get("all_rates", [])),
            "future_months": future_months_count,
            "last_scraped": last_scraped_str,
            "hours_since_scrape": round(hours_since_scrape, 1) if hours_since_scrape else None,
        },
        "scraper_metrics": {
            "consecutive_failures": _retry_state["consecutive_failures"],
            "last_success": _retry_state["last_success"].isoformat() if _retry_state["last_success"] else None,
            "hours_since_success": round(hours_since_success, 1) if hours_since_success else None,
            "last_scrape_duration_sec": round(_retry_state["last_scrape_duration"], 2),
            "rates_found_last_scrape": _retry_state["rates_found_count"],
        },
        "next_scheduled_scrape": {
            "day_of_month": 1,
            "hour": 6,
            "description": "1st of each month at 6am (skips if sufficient data)",
        },
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
        "januari": 1,
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
        "januari": 1,
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

    Handles both formats:
    - Period and rate on SAME line: "1 – 31 Januari 2026 -4.99 sen / kWj"
    - Period and rate on SEPARATE lines (legacy support)
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

        if "unjuran 3-bulan" in lower_line or "unjuran" in lower_line:
            in_current_section = False
            continue

        if not in_current_section:
            continue

        # Look for 'sen / kWj' or 'sen/kwj' in the line
        if "sen" in lower_line and "kw" in lower_line:
            # Skip if this is a header line (contains "Tempoh")
            if "tempoh" in lower_line:
                logger.debug(f"Skipping header line: {line}")
                continue
            
            # STRATEGY 1: Try parsing period and rate from SAME line
            period_info = _parse_period(line)
            rate_match = re.search(r"(-?\d+\.?\d*)\s*sen", line)
            
            if period_info and rate_match:
                start_month, end_month, year = period_info
                rate_sen = float(rate_match.group(1))
                
                # Extract clean period text (everything before the rate)
                period_text = line.split(str(rate_match.group(1)))[0].strip()
                # Remove trailing dashes/whitespace
                period_text = period_text.rstrip(" –-—\t")
                
                results.append({
                    "period": period_text if period_text else line.split("sen")[0].strip(),
                    "rate_sen": rate_sen,
                    "rate_rm": rate_sen / 100.0,
                    "start_month": start_month,
                    "end_month": end_month,
                    "year": year,
                })
                logger.debug(f"Parsed (same line): {year}-{start_month:02d} = {rate_sen} sen")
                continue
            
            # STRATEGY 2: Try parsing period from PREVIOUS line (legacy)
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
                        logger.debug(f"Parsed (tab-separated): {year}-{start_month:02d} = {rate_sen} sen")
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
                    logger.debug(f"Parsed (separate lines): {year}-{start_month:02d} = {rate_sen} sen")

    # Pass 2: if we found nothing (maybe headings changed), fall back to
    # scanning the whole page like before.
    if not results:
        logger.warning("Pass 1 found nothing, trying full-page scan...")
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if "sen" in lower_line and "kw" in lower_line:
                if "tempoh" in lower_line:
                    continue
                
                # Try same line first
                period_info = _parse_period(line)
                rate_match = re.search(r"(-?\d+\.?\d*)\s*sen", line)
                
                if period_info and rate_match:
                    start_month, end_month, year = period_info
                    rate_sen = float(rate_match.group(1))
                    period_text = line.split(str(rate_match.group(1)))[0].strip().rstrip(" –-—\t")
                    
                    results.append({
                        "period": period_text if period_text else line.split("sen")[0].strip(),
                        "rate_sen": rate_sen,
                        "rate_rm": rate_sen / 100.0,
                        "start_month": start_month,
                        "end_month": end_month,
                        "year": year,
                    })
                    continue
                
                # Legacy fallback
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
    
    # Filter out spurious entries with parentheses (e.g., "(1 Julai 2025)")
    # These are usually footnotes or historical references, not current AFA rates
    filtered_results = [r for r in results if "(" not in r["period"] and ")" not in r["period"]]
    
    # Deduplicate results (keep first occurrence)
    seen = set()
    unique_results = []
    for r in filtered_results:
        key = (r["year"], r["start_month"], r["end_month"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
    
    logger.info(f"Extracted {len(unique_results)} AFA rates (filtered {len(results) - len(filtered_results)} spurious entries)")
    
    return unique_results


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

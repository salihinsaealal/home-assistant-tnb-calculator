#!/usr/bin/env python3
"""Test script to verify TNB holiday compliance."""
import sys
import json
from urllib.request import urlopen
from urllib.parse import urlencode

CALENDARIFIC_BASE_URL = "https://calendarific.com/api/v2"
CALENDARIFIC_HOLIDAYS_ENDPOINT = "/holidays"

# TNB's official 15 holidays
TNB_OFFICIAL_HOLIDAYS = [
    "Hari Tahun Baharu (New Year's Day)",
    "Hari pertama Tahun Baharu Cina (Chinese New Year Day 1)",
    "Hari kedua Tahun Baharu Cina (Chinese New Year Day 2)",
    "Hari pertama Hari Raya Aidilfitri (Eid Day 1)",
    "Hari kedua Hari Raya Aidilfitri (Eid Day 2)",
    "Hari Pekerja (Labour Day)",
    "Hari Wesak (Wesak Day)",
    "Hari Keputeraan Yang di-Pertuan Agong (King's Birthday)",
    "Hari Raya Aidiladha (Eid al-Adha) - 1 day only",
    "Awal Muharram (Islamic New Year)",
    "Hari Kemerdekaan (Independence Day - Aug 31)",
    "Hari Malaysia (Malaysia Day - Sep 16)",
    "Maulidur Rasul (Prophet's Birthday)",
    "Hari Deepavali (Deepavali)",
    "Hari Krismas (Christmas)",
]


def simulate_integration_logic(api_key: str, year: int = 2025):
    """Simulate what the integration will do with the fix."""
    url = f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}"
    params = {
        "api_key": api_key,
        "country": "MY",
        "year": year,
        "type": "national",
    }
    
    print(f"🔍 Simulating TNB Calculator Integration Logic for {year}\n")
    print("=" * 80)
    
    full_url = f"{url}?{urlencode(params)}"
    holiday_cache = {}
    
    try:
        with urlopen(full_url, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                holidays = data.get("response", {}).get("holidays", [])
                
                print(f"📡 Step 1: Fetched {len(holidays)} holidays from Calendarific API\n")
                
                # Cache all holidays (with filter)
                skipped = []
                for holiday in holidays:
                    holiday_date = holiday.get("date", {}).get("iso")
                    holiday_name = holiday.get("name", "")
                    
                    # Skip Hari Raya Haji Day 2
                    if holiday_date and "haji" in holiday_name.lower() and "day 2" in holiday_name.lower():
                        skipped.append(f"{holiday_date} - {holiday_name}")
                        continue
                    
                    if holiday_date:
                        holiday_cache[holiday_date] = holiday_name
                
                # Add New Year's Day
                new_year_date = f"{year}-01-01"
                if new_year_date not in holiday_cache:
                    holiday_cache[new_year_date] = "New Year's Day"
                    print(f"✅ Step 2: Added New Year's Day ({new_year_date})")
                
                if skipped:
                    print(f"❌ Step 3: Removed TNB non-compliant holidays:")
                    for s in skipped:
                        print(f"   - {s}")
                
                print(f"\n{'=' * 80}")
                print(f"📅 FINAL RESULT: {len(holiday_cache)} holidays (TNB expects 15)")
                print(f"{'=' * 80}\n")
                
                # Display final holidays
                sorted_holidays = sorted(holiday_cache.items())
                print(f"{'#':<4} {'DATE':<15} {'HOLIDAY NAME':<50}")
                print("=" * 80)
                for idx, (date, name) in enumerate(sorted_holidays, 1):
                    print(f"{idx:<4} {date:<15} {name:<50}")
                
                print("\n" + "=" * 80)
                print(f"✅ Total: {len(holiday_cache)} holidays")
                
                if len(holiday_cache) == 15:
                    print("✅ MATCHES TNB's 15 official holidays!")
                else:
                    print(f"⚠️  Expected 15, got {len(holiday_cache)}")
                
                # Show TNB's official list
                print("\n" + "=" * 80)
                print("📋 TNB's Official Holiday List:")
                print("=" * 80)
                for idx, holiday in enumerate(TNB_OFFICIAL_HOLIDAYS, 1):
                    print(f"{idx:2}. {holiday}")
                
    except Exception as ex:
        print(f"❌ Error: {ex}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_tnb_holidays.py <API_KEY> [year]")
        sys.exit(1)
    
    api_key = sys.argv[1]
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    
    simulate_integration_logic(api_key, year)


if __name__ == "__main__":
    main()

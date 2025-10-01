#!/usr/bin/env python3
"""Test script to verify Calendarific API holidays for Malaysia."""
import sys
import json
from urllib.request import urlopen
from urllib.parse import urlencode
from datetime import datetime

CALENDARIFIC_BASE_URL = "https://calendarific.com/api/v2"
CALENDARIFIC_HOLIDAYS_ENDPOINT = "/holidays"


def fetch_holidays(api_key: str, year: int = 2025):
    """Fetch holidays from Calendarific API."""
    url = f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}"
    params = {
        "api_key": api_key,
        "country": "MY",  # Malaysia
        "year": year,
        "type": "national",  # Only national holidays
    }
    
    print(f"🔍 Fetching holidays for Malaysia (MY) - Year {year}")
    print(f"📡 API URL: {url}")
    print(f"📋 Parameters: country=MY, year={year}, type=national\n")
    
    full_url = f"{url}?{urlencode(params)}"
    
    try:
        with urlopen(full_url, timeout=10) as response:
            status = response.status
            print(f"📊 HTTP Status: {status}")
            
            if status == 200:
                data = json.loads(response.read().decode('utf-8'))
                holidays = data.get("response", {}).get("holidays", [])
                
                print(f"✅ Success! Found {len(holidays)} national holidays\n")
                print("=" * 80)
                print(f"{'#':<4} {'DATE':<15} {'HOLIDAY NAME':<50}")
                print("=" * 80)
                
                for idx, holiday in enumerate(holidays, 1):
                    date_iso = holiday.get("date", {}).get("iso", "N/A")
                    name = holiday.get("name", "Unknown")
                    description = holiday.get("description", "")
                    holiday_type = holiday.get("type", [])
                    
                    print(f"{idx:<4} {date_iso:<15} {name:<50}")
                    if description:
                        print(f"     {'Description:':<15} {description}")
                    print(f"     {'Types:':<15} {', '.join(holiday_type)}")
                    print()
                
                print("=" * 80)
                print(f"\n📅 Total holidays: {len(holidays)}")
                
                # Show what would be cached
                print("\n💾 Holiday cache format (what integration stores):")
                print("{")
                for holiday in holidays:
                    date_iso = holiday.get("date", {}).get("iso", "N/A")
                    print(f'  "{date_iso}": true,')
                print("}")
                
            else:
                print(f"❌ Error: HTTP {status}")
                text = response.read().decode('utf-8')[:200]
                print(f"Response: {text}")
                
    except Exception as ex:
        print(f"❌ Error: {ex}")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("❌ Usage: python test_calendarific_api.py <YOUR_API_KEY> [year]")
        print("\n💡 Get your free API key from: https://calendarific.com")
        print("   Free tier: 1000 calls/month")
        sys.exit(1)
    
    api_key = sys.argv[1]
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    
    fetch_holidays(api_key, year)


if __name__ == "__main__":
    main()

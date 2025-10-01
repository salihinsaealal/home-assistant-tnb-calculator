# Release Notes - Version 3.1.0

## 🐛 Bug Fixes

### ToU Cost Calculation Fix
**Critical bug fixed**: ToU cost was incorrectly showing lower than non-ToU during peak hours.

**Root Cause**: 
- Export energy allocation was using `export_peak = import_peak` without checking actual export
- When `export_total = 0` but `import_peak = 0.789`, it created phantom export of 0.789 kWh
- This generated incorrect NEM rebates, artificially lowering ToU cost

**Solution**:
```python
# Before (WRONG):
export_peak = import_peak
export_offpeak = export_total - export_peak  # Could be negative!

# After (CORRECT):
export_peak = min(import_peak, export_total)
export_offpeak = export_total - export_peak
```

**Impact**: ToU cost now correctly shows higher than non-ToU during peak hours, as expected.

---

## 🚀 Improvements

### 1. Robust Holiday Caching with Daily Refresh

**Problem**: 
- Holiday cache was only in memory (lost on restart)
- Only fetched when date not in cache (no retry on failure)
- If first fetch failed, never retried

**Solution**:
- ✅ **Daily API refresh**: Fetches entire year once per 24 hours
- ✅ **Persistent storage**: Holiday cache saved to disk
- ✅ **Automatic retry**: If previous fetch failed, retries next day
- ✅ **Graceful fallback**: Uses cached data if API unavailable

**API Usage**: ~30 calls/month (3% of free tier quota)

**Benefits**:
- More reliable holiday detection
- Survives Home Assistant restarts
- Automatic recovery from API failures

---

### 2. Data Persistence Across Delete/Re-add

**Problem**:
- Storage used `entry_id` which changes when integration is deleted and re-added
- All monthly data lost when reconfiguring

**Solution**:
- ✅ **Stable storage identifier**: Uses import entity ID instead of entry_id
- ✅ **Automatic migration**: Existing users' data migrated seamlessly
- ✅ **Delete-safe**: Data survives integration delete/re-add operations

**Example**:
```
Old: .storage/tnb_calculator_monthly_data_abc123  (entry_id)
New: .storage/tnb_calculator_monthly_data_electricity_import_total  (entity-based)
```

**Benefits**:
- Reconfigure integration without losing data
- More reliable data preservation
- Easier troubleshooting and migration

---

## 📝 Technical Changes

### Modified Files:
1. **sensor.py**
   - Fixed export allocation logic in `_calculate_tou_costs()`
   - Added `_fetch_holidays_if_needed()` for daily API refresh
   - Updated `_is_holiday()` to use cached data
   - Changed storage identifier to use import entity
   - Added automatic migration from old storage format
   - Updated storage format to include holiday cache and timestamp

2. **manifest.json**
   - Version bumped to 3.1.0

3. **CHANGELOG.md**
   - Added comprehensive release notes

### Storage Format Update:
```json
{
  "monthly_data": {
    "month": 10,
    "year": 2025,
    "import_total": 125.5,
    "export_total": 45.2,
    "import_peak": 75.3,
    "import_offpeak": 50.2,
    "import_last": 5432.1,
    "export_last": 1234.5
  },
  "holiday_cache": {
    "2025-01-01": true,
    "2025-08-31": true,
    ...
  },
  "last_holiday_fetch": "2025-10-01T08:15:30+08:00"
}
```

---

## 🔄 Migration Notes

### For Existing Users:
- **Automatic migration** on first restart after update
- No manual action required
- Check logs for: `Successfully migrated data from old storage`
- Old storage file kept as backup

### What to Expect:
1. First restart: Data migrated to new storage location
2. Holiday cache rebuilt from API (if 24h passed)
3. All sensor values preserved
4. No configuration changes needed

---

## 📊 Testing Performed

### Test Cases:
1. ✅ ToU cost higher than non-ToU during peak hours
2. ✅ ToU cost lower than non-ToU during off-peak hours
3. ✅ Zero export doesn't create phantom rebates
4. ✅ Holiday cache persists across restarts
5. ✅ Daily API refresh works correctly
6. ✅ Data migration from old storage format
7. ✅ Delete/re-add preserves data

### Test Data:
```
Input:
- Import Peak: 0.789 kWh
- Import Off-Peak: 0.0 kWh
- Export: 0.0 kWh
- Period: Peak (Weekday 2PM-10PM)

Results:
- Non-ToU Cost: 0.15 RM
- ToU Cost: 0.17 RM ✓ (correctly higher)
```

---

## 🎯 Summary

This release focuses on **reliability and correctness**:
- Fixed critical ToU calculation bug
- Improved holiday caching robustness
- Enhanced data persistence across configuration changes
- Better user experience with automatic migration

**Recommended for all users** - especially those using ToU tariff.

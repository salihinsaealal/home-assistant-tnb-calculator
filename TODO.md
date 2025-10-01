# TNB Calculator - Future Improvements

**Sorted by implementation safety (lowest risk first)**

---

## ✅ Completed (v3.1.4)
- [x] Fix ToU cost calculation bug (export allocation)
- [x] Implement robust holiday caching with daily refresh
- [x] Add persistent storage for monthly data
- [x] Add storage migration from v3.0.x to v3.1.x
- [x] Fix ConfigEntryNotReady warnings
- [x] Verify calculations match TNB tariff templates

---

## 🎯 Priority 1: Safe Additions (Won't break existing functionality)

### 1. Automation Helpers
**Risk Level:** ⭐ Very Low (adds new sensors only)

**New Binary Sensors:**
- `binary_sensor.tnb_peak_period` - Currently in peak period (True/False)
- `binary_sensor.tnb_high_usage_alert` - Usage approaching next tier threshold
- `binary_sensor.tnb_holiday_today` - Today is a public holiday

**New Sensors:**
- `sensor.tnb_current_period_status` - "Peak", "Off-Peak (Weekend)", "Off-Peak (Holiday)"
- `sensor.tnb_days_until_reset` - Days until monthly reset

**Benefits:**
- Easy automation triggers (e.g., "notify when peak period starts")
- Load shifting reminders
- No changes to existing calculation logic

**Implementation:**
- Add to `BASE_SENSOR_TYPES` and `TOU_SENSOR_TYPES` in `const.py`
- Add calculated values in `_async_update_data()`
- Update `sensor_definitions` in coordinator

---

### 2. Cost Prediction
**Risk Level:** ⭐ Very Low (read-only calculations)

**New Sensors:**
- `sensor.tnb_predicted_monthly_cost` - Projected end-of-month bill
- `sensor.tnb_daily_average_cost` - Average cost per day
- `sensor.tnb_daily_average_kwh` - Average consumption per day
- `sensor.tnb_days_remaining` - Days left in billing cycle
- `sensor.tnb_projected_vs_last_month` - Percentage difference vs last month

**Calculation Method:**
```python
days_elapsed = now.day
daily_average = current_cost / days_elapsed
days_in_month = calendar.monthrange(now.year, now.month)[1]
predicted_cost = daily_average * days_in_month
```

**Benefits:**
- Budget planning
- Early warning if bill will be higher than expected
- Trend analysis

**Implementation:**
- Add prediction calculations in `_async_update_data()`
- Store last month's data for comparison
- No changes to core calculation logic

---

### 3. Diagnostic Tools
**Risk Level:** ⭐ Very Low (read-only debug features)

**New Diagnostic Sensors:**
- `sensor.tnb_storage_health` - "OK", "Missing", "Corrupted"
- `sensor.tnb_last_api_call` - Timestamp of last Calendarific API call
- `sensor.tnb_cached_holidays_count` - Number of holidays in cache
- `sensor.tnb_storage_file_size` - Size of storage file in bytes

**New Service:**
- `tnb_calculator.compare_with_bill` - Input actual TNB bill, get difference report
  ```yaml
  service: tnb_calculator.compare_with_bill
  data:
    actual_bill: 156.50
  ```
  Returns:
  - Calculated: RM 154.23
  - Difference: RM -2.27 (-1.5%)

**Debug Mode:**
- Add `debug: true` option in config flow
- Enables verbose logging
- Adds detailed attributes to sensors

**Benefits:**
- Easy troubleshooting
- Bill verification
- Storage health monitoring

**Implementation:**
- Add diagnostic sensors to `const.py`
- Add service in `__init__.py`
- Add storage validation in `_load_monthly_data()`

---

## 🎯 Priority 2: Low-Risk Enhancements

### 4. Configuration Validation
**Risk Level:** ⭐⭐ Low (validates config, doesn't change logic)

**Validation Checks:**

1. **Entity Type Validation:**
   ```python
   # In config_flow.py
   entity = hass.states.get(import_entity)
   if entity.attributes.get("unit_of_measurement") not in ["kWh", "Wh"]:
       errors["import_entity"] = "not_energy_sensor"
   ```

2. **API Key Validation:**
   ```python
   # Test API key during setup
   response = await test_calendarific_api(api_key)
   if response.status != 200:
       errors["calendarific_api_key"] = "invalid_api_key"
   ```

3. **Entity State Validation:**
   ```python
   # Check if entity has numeric state
   try:
       float(entity.state)
   except ValueError:
       errors["import_entity"] = "non_numeric_state"
   ```

**Benefits:**
- Prevents common setup mistakes
- Better error messages
- Cleaner user experience

**Implementation:**
- Add validation functions in `config_flow.py`
- Add error string translations
- No changes to sensor.py

---

### 5. UI Enhancements
**Risk Level:** ⭐⭐ Low (separate frontend code)

**Custom Lovelace Card:**
- Create `www/tnb-calculator-card.js`
- Visual bill breakdown
- Peak vs off-peak usage charts
- Monthly comparison graph

**Card Features:**
```yaml
type: custom:tnb-calculator-card
entity: sensor.tnb_total_cost
show_breakdown: true
show_chart: true
chart_days: 30
```

**Example Display:**
```
╔════════════════════════════════════╗
║   TNB Calculator - October 2025    ║
╠════════════════════════════════════╣
║  Current Bill:        RM 154.23    ║
║  Predicted:           RM 465.69    ║
║  Last Month:          RM 432.10    ║
║  Difference:          +7.8% ↑      ║
╠════════════════════════════════════╣
║  Import:    125.5 kWh              ║
║    Peak:     75.3 kWh (60%)        ║
║    Off-Peak: 50.2 kWh (40%)        ║
║  Export:     45.2 kWh              ║
╠════════════════════════════════════╣
║  [====== Peak ====== Off-Peak ]=   ║
║   60%                 40%           ║
╚════════════════════════════════════╝
```

**Benefits:**
- Better visualization
- Quick bill overview
- Mobile-friendly

**Implementation:**
- Create separate JS file for card
- Add to HACS frontend resources
- Document in README
- Won't affect backend at all

---

## 🎯 Priority 3: Medium-Risk Improvements

### 6. Better Error Recovery
**Risk Level:** ⭐⭐⭐ Medium (modifies existing logic)

**Enhancements:**

1. **Graceful Sensor Unavailability:**
   ```python
   # If sensor unavailable, use last known value
   if entity.state == "unavailable":
       _LOGGER.warning("Sensor unavailable, using last value")
       return self._monthly_data.get(last_key, 0)
   ```

2. **Data Interpolation:**
   ```python
   # If gap in data, estimate based on average
   if time_gap > timedelta(hours=1):
       estimated_delta = hourly_average * hours_gap
   ```

3. **Health Check Sensor:**
   ```python
   sensor.tnb_health_status = {
       "status": "healthy",
       "last_update": "2025-10-01 19:00:00",
       "import_sensor": "available",
       "export_sensor": "available",
       "api_status": "ok",
       "storage_status": "ok"
   }
   ```

**Benefits:**
- More resilient to temporary issues
- Better handling of sensor outages
- Automatic recovery

**Implementation:**
- Modify `_get_entity_state()` for fallbacks
- Add interpolation in `_compute_delta()`
- Add health tracking
- **Risk:** Could mask real issues if not careful

---

### 7. Energy Dashboard Integration
**Risk Level:** ⭐⭐⭐ Medium (new integration points)

**Integration Features:**

1. **Register as Energy Source:**
   ```python
   async def async_get_config_entry_diagnostics(hass, entry):
       # Provide energy data for dashboard
       return {
           "energy_consumption": import_total,
           "energy_production": export_total,
           "cost": total_cost,
       }
   ```

2. **Add to Energy Flow:**
   - Import energy contribution
   - Export energy contribution
   - Cost tracking

3. **Visual Integration:**
   - Appears in Energy dashboard automatically
   - Shows costs alongside kWh
   - Historical data visualization

**Benefits:**
- Native HA Energy dashboard integration
- Better visualization
- Standardized interface

**Implementation:**
- Implement energy platform
- Add cost_sensor to energy config
- Register sensors properly
- **Risk:** Requires understanding HA Energy platform API

---

## 📝 Implementation Order Recommendation

**Phase 1 (v3.2.0):** Automation Helpers
- Lowest risk
- High user value
- Easy to implement
- ~2-3 hours work

**Phase 2 (v3.3.0):** Cost Prediction + Diagnostic Tools
- Still low risk
- Very useful features
- ~4-5 hours work

**Phase 3 (v3.4.0):** Configuration Validation
- Improves setup experience
- Prevents errors
- ~3-4 hours work

**Phase 4 (v3.5.0):** UI Enhancements
- Separate from core logic
- Big UX improvement
- ~6-8 hours work

**Phase 5 (v4.0.0):** Better Error Recovery + Energy Dashboard
- More complex
- Requires testing
- ~8-10 hours work

---

## 🧪 Testing Strategy

For each feature:
1. ✅ Unit tests for calculations
2. ✅ Integration tests with mocked entities
3. ✅ Manual testing on real HA instance
4. ✅ Verify storage migration still works
5. ✅ Check backwards compatibility
6. ✅ Test with/without ToU mode
7. ✅ Test with/without export

---

## 📚 Documentation Updates Needed

For each feature:
- [ ] Update README.md with new sensors
- [ ] Update CHANGELOG.md
- [ ] Add examples to documentation
- [ ] Update troubleshooting guide
- [ ] Add screenshots if UI changes

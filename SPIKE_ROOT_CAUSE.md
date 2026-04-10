# Spike Detection Error - Root Cause Analysis

## Your Error

```
Spike detected for import_last: delta=12514.781 kWh exceeds threshold of 10.0 kWh. 
Previous=0.000, Current=12514.781. Ignoring this reading to prevent data corruption.
```

## What Could Cause `import_last` and `export_last` to Reset to 0?

Based on code analysis, here are **all possible causes**:

---

### 1. **Monthly Billing Cycle Reset** (Most Likely)

**When:** Your billing period changed (crossed billing start day)

**What happens:**
- Line 482-483 in `sensor.py`: `if self._month_changed(now): self._monthly_data = self._create_month_bucket(now)`
- Line 1551-1552 in `_create_month_bucket()`: Sets `import_last` and `export_last` to **current sensor values**

**Expected behavior:**
- Should read your sensor's current value (e.g., 12514.781 kWh)
- If sensor returns `None` or is unavailable → falls back to 0

**Root cause if this happened:**
```python
# Line 1551-1552
"import_last": self._get_entity_state(self._import_entity, "Import entity", is_optional=False),
"export_last": self._get_entity_state(self._export_entity, "Export entity", is_optional=True),
```

If `_get_entity_state()` returned `0.0` or `None` at the moment of monthly reset, your baseline gets set to 0.

**Possible reasons:**
- Your energy sensor was unavailable during the reset
- Home Assistant was restarting during the billing cycle transition
- Sensor had a temporary glitch returning 0 or unknown state

---

### 2. **Manual Storage Reset Service**

**When:** Someone (or an automation) called:
```yaml
service: tnb_calculator.reset_storage
data:
  confirm: "RESET"
```

**What happens:**
- Line 365-387 in `sensor.py`: Deletes storage file and recreates fresh buckets
- Sets `import_last`/`export_last` to current sensor values (same as monthly reset)

**Check:** Look in your Home Assistant logs for:
```
Resetting TNB Calculator storage and runtime buffers
```

---

### 3. **Integration Reinstall/Reconfigure**

**When:**
- You deleted and re-added the integration
- You changed the import entity in configuration
- Storage file got corrupted or deleted manually

**What happens:**
- Storage identifier changes when import entity changes
- New storage file created with fresh data
- `_create_month_bucket()` called, reads sensor state at that moment

---

### 4. **Storage File Corruption or Manual Delete**

**When:**
- Storage file manually deleted: `<config>/.storage/tnb_calculator_monthly_data_*`
- File became corrupted (disk error, incomplete write)
- Backup restored without storage files

**What happens:**
- `_load_monthly_data()` finds no stored data (line 214)
- Falls back to creating new bucket
- Reads current sensor state

---

### 5. **Sensor Was Actually at 0**

**When:** Your energy sensor entity was reporting 0 at the time of:
- Monthly reset
- Integration reload
- Storage recreation

**Common causes:**
- Utility meter helper was reset
- Sensor integration restarted
- Template sensor had a temporary calculation error
- Database purge removed sensor history

---

## How to Diagnose What Happened to You

### Check 1: Look for Monthly Reset
```bash
# In Home Assistant logs, search for:
"Saved month 2026-01 to historical data"
"Day changed from"
```

If you see this around the time the error started, it was a monthly reset.

### Check 2: Look for Manual Reset
```bash
# Search logs for:
"Resetting TNB Calculator storage and runtime buffers"
```

### Check 3: Check Your Sensor State History
1. Go to Home Assistant → Developer Tools → States
2. Find your import/export sensor entities
3. Check history graph around when error started
4. Look for:
   - Gaps (unavailable state)
   - Drops to 0
   - Unknown state

### Check 4: Check Integration Events
```bash
# Search logs for:
"Using storage key:"
"Loaded monthly data from storage"
"No valid monthly data in storage"
```

If you see "No valid monthly data", storage was empty/corrupted.

### Check 5: Check Your Billing Cycle
- What day is your billing start day configured?
- Did today or yesterday cross that day?

Example: If billing starts on day 20, and today is Jan 20th → monthly reset occurred.

---

## Most Likely Scenario for You

Based on "this happen today", the most probable cause is:

**Monthly billing cycle reset occurred, and at that exact moment, your energy sensor was returning 0, unavailable, or unknown state.**

Timeline:
1. Your billing period changed (crossed billing start day)
2. Integration called `_create_month_bucket()`
3. `_get_entity_state()` read your sensor at that moment
4. Sensor returned 0 or unavailable → baseline set to 0
5. Next update (5 min later), sensor shows 12514 kWh
6. Delta = 12514 - 0 = 12514 kWh → spike detected → rejected

---

## Prevention Strategies

### 1. Ensure Sensor Stability
Make sure your import/export energy sensors:
- Never reset to 0 (use `total_increasing` sensors)
- Don't depend on integrations that might be unavailable during HA startup
- Have fallback values if calculated from templates

### 2. Use Utility Meter Properly
If using Home Assistant's Utility Meter:
```yaml
utility_meter:
  monthly_energy:
    source: sensor.your_cumulative_energy
    cycle: monthly  # Don't reset the source sensor!
```

The source sensor should **never reset** - only the utility meter resets.

### 3. Add Sensor Availability Check
Consider adding automation to notify if sensors go unavailable:
```yaml
automation:
  - alias: "Energy Sensor Availability Alert"
    trigger:
      - platform: state
        entity_id: 
          - sensor.your_import_energy
          - sensor.your_export_energy
        to: "unavailable"
        for: "00:01:00"
    action:
      - service: notify.notify
        data:
          message: "Energy sensor unavailable - TNB Calculator may lose baseline!"
```

---

## Fix Options (Same as Before)

### Quick Fix (Recommended)
```yaml
service: tnb_calculator.reset_storage
data:
  confirm: "RESET"
```

### Preserve-Data Fix
```yaml
# Option A: Reset baselines to 0, keep monthly totals
service: tnb_calculator.set_import_energy_values
data:
  import_total: 0  # Or your current month's actual usage
  distribution: "auto"
```

### Manual Storage Edit
Stop HA, edit `.storage/tnb_calculator_monthly_data_*`, update:
```json
{
  "import_last": 12514.781,
  "export_last": 10643.540
}
```

---

## Long-term Solution

Add this to your integration's initialization to detect and warn about sensor state issues:

**Already implemented in code (line 1551-1552):**
```python
"import_last": self._get_entity_state(self._import_entity, "Import entity", is_optional=False),
```

**What `_get_entity_state()` should do:**
- Check if sensor exists
- Check if state is numeric
- Log warning if unavailable
- Return last known good value or 0 as fallback

If this is happening frequently, the integration could be enhanced to:
1. Store last known good sensor values
2. Use those if sensor is unavailable during reset
3. Add validation before accepting 0 as baseline

---

## Summary

**Today's error was most likely caused by:**
- Billing cycle reset triggered
- Your energy sensor was temporarily unavailable/0 during reset
- Baseline got set to 0 instead of ~12515 kWh
- Next reading triggered spike detection

**Quick fix:** Use `reset_storage` service

**Prevention:** Ensure your energy sensors are always available and never reset to 0

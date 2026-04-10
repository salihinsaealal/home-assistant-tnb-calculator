# Router Reset / Integration Reconnect - Baseline Corruption Fix

## What Happened to You

**Timeline:**
1. You reset your router
2. All integrations disconnected from Home Assistant
3. TNB Calculator's 5-minute update cycle ran while energy sensors were still reconnecting
4. Energy sensors returned "unavailable" state
5. Code returned `0.0` as fallback (line 1423-1426 in sensor.py)
6. This `0.0` got written as the new baseline in storage
7. Sensors reconnected and reported actual values (~12515 kWh)
8. Integration calculated delta: `12515 - 0 = 12515 kWh` in 5 minutes
9. Spike detection triggered → readings rejected → no data recorded

**This is NOT a billing cycle issue** - it happens mid-month during integration reconnects.

---

## The Fix (Already Applied)

I've modified `_create_month_bucket()` in `sensor.py` to **preserve last known good baselines** when sensors are temporarily unavailable.

### Before (Vulnerable Code):
```python
"import_last": self._get_entity_state(self._import_entity, "Import entity", is_optional=False),
"export_last": self._get_entity_state(self._export_entity, "Export entity", is_optional=True),
```

Problem: If sensor unavailable → returns 0 → baseline corrupted

### After (Fixed Code):
```python
# Get current sensor readings
import_reading = self._get_entity_state(self._import_entity, "Import entity", is_optional=False)
export_reading = self._get_entity_state(self._export_entity, "Export entity", is_optional=True)

# Preserve last known good baseline if sensor is unavailable (returns 0)
if hasattr(self, "_monthly_data") and self._monthly_data:
    old_import_last = self._monthly_data.get("import_last", 0.0)
    old_export_last = self._monthly_data.get("export_last", 0.0)
    
    if import_reading == 0.0 and old_import_last > 0.0:
        _LOGGER.warning("Import sensor unavailable - preserving baseline: %.3f kWh", old_import_last)
        import_reading = old_import_last
    
    if export_reading == 0.0 and old_export_last > 0.0:
        _LOGGER.warning("Export sensor unavailable - preserving baseline: %.3f kWh", old_export_last)
        export_reading = old_export_last

"import_last": import_reading,
"export_last": export_reading,
```

**Protection:** If sensor returns 0 but we have a valid baseline stored → keep the old baseline

---

## When This Fix Applies

The fix protects against baseline corruption during:

1. **Router resets/reconnects** (your case)
2. **Home Assistant restarts** (sensors slow to initialize)
3. **Integration reloads** (energy sensor integration restarting)
4. **Network interruptions** (cloud-based energy sensors)
5. **Database maintenance** (recorder downtime)
6. **Device reboots** (smart meter/gateway restart)

---

## Immediate Fix for Your Current Issue

You still need to fix your corrupted baseline. Use this service:

```yaml
service: tnb_calculator.reset_storage
data:
  confirm: "RESET"
```

**What happens:**
1. Clears all data
2. Next update cycle reads current sensor values (e.g., 12515 kWh)
3. Sets as new baseline
4. Starts tracking deltas normally
5. **New code prevents this from happening again**

---

## Testing the Fix

After applying the fix and resetting storage, you can test the protection:

### Test 1: Simulated Integration Reload
1. Note current import value: e.g., 12515 kWh
2. Go to: Settings → Devices & Services → TNB Calculator → Reload
3. Check logs - should see "preserving baseline" warnings if sensor temporarily unavailable
4. Verify data continues recording (no spike errors)

### Test 2: Simulated Router Reset
1. Note current baseline from storage
2. Disable Wi-Fi / disconnect router
3. Wait for TNB Calculator update cycle (5 min)
4. Reconnect network
5. Check logs for baseline preservation messages
6. Verify no spike detection errors

---

## Additional Prevention Strategies

### 1. Use Local Energy Sensors (Recommended)

**Problem:** Cloud-based sensors (e.g., smart meters via cloud API) can be unavailable during network issues

**Solution:** Use local integrations when possible:
- **Shelly Energy Meters** (local MQTT/HTTP)
- **ESPHome** energy monitors (local)
- **Zigbee/Z-Wave** energy plugs (local via hub)
- **Home Assistant Energy Dashboard** utility meters (local calculation)

**Example:**
```yaml
# Bad (cloud-dependent)
sensor.tuya_energy_meter  # Goes unavailable during network issues

# Good (local)
sensor.shelly_em_channel_1_energy  # Always available via LAN
```

### 2. Add Sensor Availability Monitor

Create an automation to alert when energy sensors go unavailable:

```yaml
automation:
  - alias: "Energy Sensor Availability Alert"
    trigger:
      - platform: state
        entity_id:
          - sensor.your_import_energy_sensor
          - sensor.your_export_energy_sensor
        to: "unavailable"
        for: "00:02:00"
    action:
      - service: persistent_notification.create
        data:
          title: "⚠️ Energy Sensor Unavailable"
          message: >
            {{ trigger.entity_id }} is unavailable. 
            TNB Calculator baseline may be at risk if this persists.
      - service: notify.mobile_app_your_phone
        data:
          message: "Energy sensor unavailable: {{ trigger.entity_id }}"
```

### 3. Use Battery Backup for Network Equipment

**Prevents:** Router/modem power loss during outages
**Cost:** ~$50-100 for small UPS
**Benefit:** Keeps network stable during brief power interruptions

### 4. Stagger Integration Startup (Advanced)

If using Home Assistant OS/Core, add startup delays to ensure energy sensors initialize before TNB Calculator:

```yaml
# configuration.yaml
homeassistant:
  customize:
    sensor.tnb_calculator_total_cost_tou:
      # TNB Calculator loads after energy integrations stabilize
```

*Note: This is complex and not recommended for most users*

---

## How to Check If You're Vulnerable

### Method 1: Check Sensor Type
```yaml
# In Developer Tools → States
sensor.your_import_energy_sensor
```

Look at "Integration" attribute:
- ✅ **Local:** Shelly, ESPHome, MQTT, Zigbee, Z-Wave, Modbus
- ⚠️ **Cloud:** Tuya, Smart Life, some proprietary apps

### Method 2: Test Sensor Stability
1. Disconnect router for 2 minutes
2. Reconnect
3. Check sensor state in Developer Tools
4. If sensor shows "unavailable" for >30 seconds → vulnerable

---

## Long-term Architecture Improvement (Future)

For even better protection, the integration could:

1. **Add baseline validation** - reject baselines that drop >50% from previous
2. **Store baseline history** - keep last 3 baselines as fallback
3. **Add recovery mode** - detect baseline corruption and auto-recover
4. **Implement retry logic** - wait for sensors to stabilize before creating buckets

These improvements could be added in a future version.

---

## Summary

**Your issue:** Router reset → sensors unavailable → baseline set to 0 → data rejected

**The fix:** Code now preserves last known baseline when sensors unavailable

**Action needed:** 
1. Apply the code fix (already done above)
2. Run `reset_storage` service to clear corrupted baseline
3. Consider using local energy sensors for better reliability

**Prevention:** Fixed code + local sensors = no more baseline corruption during network issues

---

## Version Note

This fix should be included in the next release (v4.4.8+). Add to CHANGELOG:

```
### Fixed
- Baseline corruption during router/integration reconnects
- Integration now preserves last known sensor baseline when sensors temporarily unavailable
- Prevents spike detection errors after network interruptions
```

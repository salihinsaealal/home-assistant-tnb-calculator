# Fix: Spike Detection Error

## Problem

You're seeing this error:
```
Spike detected for import_last: delta=12514.781 kWh exceeds threshold of 10.0 kWh. 
Previous=0.000, Current=12514.781. Ignoring this reading to prevent data corruption.
```

This happens when:
- The integration's baseline (`import_last`/`export_last`) is at 0
- Your actual energy sensors are reading large cumulative values (e.g., 12515 kWh)
- The delta exceeds the spike detection threshold (10 kWh per 5-minute interval)

**Common causes:**
- Monthly billing cycle reset occurred while energy sensor was temporarily unavailable
- Storage was manually reset or corrupted
- Integration was reinstalled
- Energy sensor reset to 0 (shouldn't happen with `total_increasing` sensors)

For detailed root cause analysis, see `SPIKE_ROOT_CAUSE.md`.

## Solution Options

### Option 1: Reset Storage and Let Integration Relearn (Easiest)

**Warning:** This clears all monthly data.

```yaml
service: tnb_calculator.reset_storage
data:
  confirm: "RESET"
```

After reset:
1. Integration reloads
2. Next update cycle will use your current sensor values as the new baseline
3. Data collection resumes normally

**Downside:** Loses current month's accumulated data.

---

### Option 2: Use Calibration Service (Preserves Data)

Set the integration's baseline to match your current sensor readings:

#### Step 1: Get your current sensor values

Check in Home Assistant:
- `sensor.your_import_energy_sensor` → e.g., 12514.78 kWh
- `sensor.your_export_energy_sensor` → e.g., 10643.54 kWh

#### Step 2: Calibrate import energy

```yaml
service: tnb_calculator.set_import_energy_values
data:
  import_total: 0  # Start fresh for the month
  distribution: "auto"
```

#### Step 3: Calibrate export energy (if you have solar)

```yaml
service: tnb_calculator.set_export_energy_values
data:
  export_total: 0  # Start fresh for the month
```

#### Step 4: Reload integration

Settings → Devices & Services → TNB Calculator → ⋮ → Reload

**Note:** This sets your monthly totals to 0 but updates the baseline. Next update will calculate deltas correctly.

---

### Option 3: Manual Storage Edit (Advanced)

**Warning:** Edit while Home Assistant is stopped. Backup first.

#### Location:

Home Assistant storage file:
```
<config_dir>/.storage/tnb_calculator_monthly_data_<entry_id>
```

Example paths:
- **Docker:** `/config/.storage/tnb_calculator_monthly_data_xxxxx`
- **Home Assistant OS:** `/config/.storage/tnb_calculator_monthly_data_xxxxx`
- **macOS:** `~/Library/Application Support/io.homeassistant.xxxxx/.storage/`

#### Steps:

1. **Stop Home Assistant**

2. **Backup the file:**
   ```bash
   cp .storage/tnb_calculator_monthly_data_xxxxx .storage/tnb_calculator_monthly_data_xxxxx.backup
   ```

3. **Edit the file** and find these keys:
   ```json
   {
     "data": {
       "import_last": 0.0,
       "export_last": 0.0,
       "import_total": 0.0,
       "export_total": 0.0,
       ...
     }
   }
   ```

4. **Update to match your sensor values:**
   ```json
   {
     "data": {
       "import_last": 12514.781,
       "export_last": 10643.540,
       "import_total": 0.0,
       "export_total": 0.0,
       ...
     }
   }
   ```

   This tells the integration:
   - Last seen import: 12514.781 kWh (matches your sensor)
   - Last seen export: 10643.540 kWh (matches your sensor)
   - Monthly totals remain at 0 (fresh start for billing cycle)

5. **Start Home Assistant**

6. **Verify** - check logs for successful update without spike warnings

---

## Why This Happens

The integration tracks two values:
1. **`import_last` / `export_last`**: Last reading from your sensor (baseline)
2. **`import_total` / `export_total`**: Accumulated usage this billing cycle

When you:
- Reinstall the integration
- Delete and re-add it
- Storage gets corrupted

The baseline resets to 0, but your utility meter sensor still reports cumulative lifetime values (e.g., 12515 kWh).

The spike detection sees: `12515 - 0 = 12515 kWh` in 5 minutes → impossible → ignored.

---

## Recommended Approach

**For immediate fix with minimal disruption:**

Use **Option 1** (reset storage) if you're early in the billing cycle.

Use **Option 2** (calibration service) if you want to preserve some monthly data and are comfortable setting values manually.

Use **Option 3** (manual edit) only if you need to preserve exact monthly totals and know your way around JSON files.

---

## Prevention

The integration now includes automatic spike detection to prevent data corruption. This is working as designed. To avoid this in the future:

1. Don't delete/re-add the integration mid-cycle
2. Use the calibration services when needed
3. Use `reset_storage` service to intentionally clear data (with confirmation)

---

## Related Services

See `README.md` for full service documentation:
- `tnb_calculator.set_import_energy_values` - Set exact import values
- `tnb_calculator.adjust_import_energy_values` - Adjust by offset
- `tnb_calculator.set_export_energy_values` - Set exact export values
- `tnb_calculator.reset_storage` - Nuclear option (clears everything)

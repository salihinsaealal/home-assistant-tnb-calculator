# TNB Calculator Dashboards

This directory contains pre-built dashboard configurations for the TNB Calculator integration.

## Available Dashboards

### 1. `tnb_calculator_dashboard.yaml` (Basic)
A simple, functional dashboard using standard Home Assistant entities and ApexCharts.

**Requirements:**
- ApexCharts Card (via HACS)

**Features:**
- Basic entity cards for costs and energy
- Monthly cost comparison chart
- Daily energy flow chart

---

### 2. `tnb_calculator_bubble_modern.yaml` (Modern/Recommended ⭐)
An Apple-inspired dashboard with soft colors, clean typography, and intuitive organization.

**Requirements:**
- [Bubble Card](https://github.com/Clooos/Bubble-Card) (via HACS)
- [ApexCharts Card](https://github.com/RomRider/apexcharts-card) (via HACS)

**Design Philosophy:**
- **Soft Colors**: Subtle 12% opacity backgrounds instead of bold gradients
- **Clean Typography**: Lightweight fonts (400-600) with proper hierarchy
- **Organized Sections**: Clear headers (Overview, Energy, Cost, Today, Status, Analytics)
- **Consistent Spacing**: Apple-like margins and padding
- **Minimal Distractions**: Hidden separator lines, focus on content

**Features:**
- Soft, non-intrusive color palette
- Organized into logical sections with headers
- Consistent card sizing and spacing
- Lightweight typography (0.8em labels, 1.3em values)
- Optimized chart appearance
- Works beautifully with any dark theme

**Installation:**
1. Install Bubble Card via HACS:
   - Go to HACS → Frontend
   - Search for "Bubble Card"
   - Install and restart Home Assistant

2. Install ApexCharts Card via HACS:
   - Go to HACS → Frontend
   - Search for "ApexCharts Card"
   - Install and restart Home Assistant

3. Copy the dashboard YAML:
   - Navigate to Settings → Dashboards
   - Create a new dashboard or edit existing
   - Switch to YAML mode
   - Paste the contents of `tnb_calculator_bubble_modern.yaml`

**Sections:**
- **Overview**: Monthly Bill, Forecast, Usage Tier
- **Energy**: Import, Export, Net Energy
- **Cost Breakdown**: ToU vs Flat, Peak vs Off-Peak
- **Today**: Real-time daily import/export
- **Status**: Period, Day Type, Holiday indicators
- **Analytics**: Monthly cost trends, daily energy flow charts

---

### 3. `tnb_calculator_bubble_dashboard.yaml` (Legacy)
The original colorful version with bold gradients. Kept for users who prefer vibrant colors.

---

## Customization

### Entity Names
If you've renamed your TNB Calculator sensors, update the `entity:` fields in the YAML to match your entity IDs.

### Colors
Modify gradient colors in the `styles:` sections. Example:
```yaml
.bubble-icon-container {
  background: linear-gradient(135deg, #YOUR_COLOR_1, #YOUR_COLOR_2) !important;
}
```

### Layout
- Change `card_layout: large` to `normal` for compact cards
- Adjust `graph_span:` in ApexCharts for different time ranges
- Remove sections you don't need

---

## Troubleshooting

### "Custom element doesn't exist: bubble-card"
- Install Bubble Card via HACS
- Clear browser cache (Ctrl+F5 or Cmd+Shift+R)
- Restart Home Assistant

### "Custom element doesn't exist: apexcharts-card"
- Install ApexCharts Card via HACS
- Clear browser cache
- Restart Home Assistant

### Charts showing incorrect scale
- Ensure your sensors are reporting numeric values
- Check that sensor units are set correctly (kWh, RM)
- Verify `min: 0` is set in yaxis configuration

### Colors too vibrant
- Use `tnb_calculator_bubble_modern.yaml` for soft, Apple-like colors
- Or adjust opacity values in `styles:` (e.g., `rgba(255, 152, 0, 0.12)` - lower the last number)

---

## Support

For issues or questions:
1. Check the [troubleshooting guide](../troubleshooting.md)
2. Review Home Assistant logs for error messages
3. [Open an issue](https://github.com/salihinsaealal/home-assistant-tnb-calculator/issues) on GitHub

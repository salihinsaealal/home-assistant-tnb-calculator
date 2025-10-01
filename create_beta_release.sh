#!/bin/bash
# Create GitHub Release for v3.2.1 (as beta/pre-release)
# Note: HACS requires clean semantic version tags (v3.2.1, not v3.2.1-beta)
# HACS determines beta status from the GitHub release pre-release flag

gh release create v3.2.1 \
  --title "v3.2.1 - TNB Holiday Compliance Fix (BETA)" \
  --notes "## ⚠️ BETA VERSION - For Testing Only

This is a beta release for testing. Production users should use v3.1.4.

### What's New in v3.2.1-beta

#### Fixed
- **Holiday Compliance**: Fixed holiday detection to match TNB's official 15-holiday list exactly
  - ✅ Added New Year's Day (Jan 1) - TNB official holiday that Calendarific was missing
  - ✅ Removed Hari Raya Haji Day 2 - TNB only recognizes 1 day (not 2)
  - ✅ Result: Exactly 15 holidays matching TNB's tariff schedule
  - Dynamic Islamic dates still fetched from Calendarific API annually

### Testing Instructions

1. In HACS, go to TNB Calculator → ⋮ → Redownload
2. Enable \"Show beta versions\"
3. Select v3.2.1-beta
4. Test holiday detection for 2025

### Revert to Stable
If you encounter issues, redownload v3.1.4 (disable \"Show beta versions\")

**Full Changelog**: https://github.com/salihinsaealal/home-assistant-tnb-calculator/blob/beta/CHANGELOG.md" \
  --prerelease \
  --target beta

echo "✅ Beta release created!"
echo "View at: https://github.com/salihinsaealal/home-assistant-tnb-calculator/releases/tag/v3.2.1"

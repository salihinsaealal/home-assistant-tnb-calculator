# Beta Testing Guide

## ✅ Setup Complete!

### Current Branch Structure

```
master (v3.1.4)          ← Production (users get this)
  └─ beta (v3.2.1-beta)  ← Testing (you test this)
```

### Important: How HACS Detects Beta Versions

- ✅ **manifest.json** has `"version": "3.2.1"` (NOT "3.2.1-beta")
- ✅ **GitHub tag** is `v3.2.1-beta` 
- ✅ **GitHub release** must be marked as "pre-release"
- ✅ HACS uses the **pre-release flag** to determine beta status, not the version string

## For Users (Default Installation)
Users will automatically get: **v3.1.4** (stable)

## For You (Beta Testing)

### Install Beta Version

1. Open **Home Assistant**
2. Go to **HACS** → **Integrations**
3. Find **TNB Calculator**
4. Click **⋮** (three dots) → **Redownload**
5. Enable **"Show beta versions"** toggle
6. Select **v3.2.1-beta**
7. Click **Download**
8. Restart Home Assistant

### What to Test in v3.2.1-beta

✅ **Holiday Detection**
- Check if New Year's Day (Jan 1, 2025) is recognized as holiday
- Verify only 15 holidays total (not 16)
- Confirm Hari Raya Haji shows only 1 day (June 7), not 2 days

✅ **Off-Peak Detection**
- On Jan 1, 2025: Should be off-peak all day
- On June 8, 2025: Should NOT be treated as holiday (normal weekday rules)

✅ **Check Logs**
Look for these messages in Home Assistant logs:
```
Successfully cached 15 holidays for 2025 (matching TNB's 15 official holidays)
Added New Year's Day 2025-01-01 (TNB official holiday)
Skipping 2025-06-08 (TNB only recognizes 1 day of Hari Raya Haji)
```

### Revert to Stable (If Beta Fails)

1. **HACS** → **TNB Calculator** → **⋮** → **Redownload**
2. Disable "Show beta versions"
3. Select **v3.1.4**
4. Click **Download**
5. Restart Home Assistant

Your data is safe - both versions use the same storage format!

## Promote Beta to Production (After Testing)

When v3.2.1-beta is confirmed working:

```bash
# Merge beta into master
git checkout master
git merge beta

# Remove -beta suffix
# Edit manifest.json: "3.2.1-beta" → "3.2.1"
git add custom_components/tnb_calculator/manifest.json
git commit -m "release: promote v3.2.1 to stable"

# Tag as stable release
git tag v3.2.1 -m "v3.2.1: TNB holiday compliance fix"

# Push everything
git push origin master
git push origin v3.2.1

# Clean up beta tag
git push origin --delete v3.2.1-beta
git tag -d v3.2.1-beta
```

## Future Workflow

For new features:

1. Develop in `beta` branch
2. Tag as `vX.X.X-beta`
3. Test in your Home Assistant (show beta versions)
4. When stable, merge to `master` and tag `vX.X.X`

This way:
- Users always get stable releases
- You can safely test new features
- Easy rollback if issues found

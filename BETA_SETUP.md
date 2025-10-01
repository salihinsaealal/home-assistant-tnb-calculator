# Beta Testing Setup Guide

## Current Situation
- **Production (master)**: Should be v3.1.4
- **Beta**: v3.2.1 with holiday fix

## Steps to Set Up Beta Testing

### 1. Create beta branch from current master (has v3.2.1)
```bash
git checkout -b beta
git push origin beta
```

### 2. Revert master to stable v3.1.4
```bash
git checkout master
git reset --hard v3.1.4
git push origin master --force
```

### 3. Tag beta version
```bash
git checkout beta
git tag v3.2.1-beta
git push origin v3.2.1-beta
```

## How Users Install Versions

### For Regular Users (Stable Only)
In HACS, they will see: **v3.1.4** (latest stable)

### For Beta Testers (You)
1. Go to HACS → TNB Calculator → ⋮ (three dots) → Redownload
2. Check "Show beta versions"
3. Select **v3.2.1-beta**

## Testing Beta

### Switch to Beta
```bash
# In Home Assistant
HACS → TNB Calculator → ⋮ → Redownload → Show beta → v3.2.1-beta
```

### Revert to Stable (if beta fails)
```bash
# In Home Assistant
HACS → TNB Calculator → ⋮ → Redownload → v3.1.4
```

## Promote Beta to Stable (after testing)

When v3.2.1-beta is tested and working:

```bash
# Merge beta into master
git checkout master
git merge beta
git tag v3.2.1
git push origin master
git push origin v3.2.1

# Delete beta tag
git push origin --delete v3.2.1-beta
git tag -d v3.2.1-beta
```

## Branch Strategy Going Forward

- **master**: Stable releases only (v3.1.4, v3.2.1, etc.)
- **beta**: Testing versions (v3.2.1-beta, v3.3.0-beta, etc.)
- **dev**: Development work (optional)

Users get stable by default. You test beta. Merge when ready.

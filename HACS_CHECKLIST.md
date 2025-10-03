# HACS Publication Checklist

This checklist helps ensure your integration meets all HACS requirements for publication.

## ✅ Files Created/Updated

- [x] `hacs.json` - HACS manifest file with name, country, and minimum Home Assistant version
- [x] `.github/workflows/validate.yaml` - GitHub Actions for HACS and Hassfest validation
- [x] `info.md` - Enhanced description for HACS UI
- [x] `LICENSE` - MIT License file
- [x] `README.md` - Comprehensive documentation (already exists)
- [x] `manifest.json` - Integration manifest (already exists)

## 📋 Repository Requirements

### Required on GitHub:
- [ ] **Repository Description**: Add a brief description on GitHub repository settings
  - Example: "Calculate TNB electricity costs in Malaysia with ToU support"
  
- [ ] **Repository Topics**: Add relevant topics on GitHub repository settings
  - Suggested topics: `home-assistant`, `hacs`, `integration`, `malaysia`, `tnb`, `electricity`, `time-of-use`

- [ ] **Issues Enabled**: Ensure GitHub Issues are enabled in repository settings

- [ ] **GitHub Release**: Create a new release (not just a tag) after validation passes
  - Tag version: `v3.3.0` (or next version)
  - Release title: "v3.3.0 - [Brief description]"
  - Release notes: Use content from CHANGELOG.md

## 🔍 Validation Requirements

### Before Submission:
- [ ] **Push changes to GitHub**: Commit and push all new files
  ```bash
  git add hacs.json .github/ info.md LICENSE HACS_CHECKLIST.md
  git commit -m "chore: Add HACS publication files"
  git push
  ```

- [ ] **Wait for GitHub Actions**: Both HACS Action and Hassfest must pass
  - Check: https://github.com/salihinsaealal/home-assistant-tnb-calculator/actions
  - Fix any errors reported by the actions

- [ ] **Create GitHub Release**: After actions pass successfully
  - Go to: https://github.com/salihinsaealal/home-assistant-tnb-calculator/releases/new
  - Tag: `v3.3.0`
  - Title: `v3.3.0`
  - Description: Copy from CHANGELOG.md

## 📝 Optional Enhancements

- [ ] **Brands Integration**: Consider adding to [home-assistant/brands](https://github.com/home-assistant/brands)
  - This provides official logos and icons in Home Assistant UI
  - Requires separate PR to brands repository

- [ ] **My Links**: Add a HACS installation link to README
  - Use: https://my.home-assistant.io/create-link/?redirect=hacs_repository
  - Example badge for README:
    ```markdown
    [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=salihinsaealal&repository=home-assistant-tnb-calculator&category=integration)
    ```

## 🚀 Submission to HACS Default Store (Optional)

If you want your integration listed in HACS default store (not required for HACS usage):

1. Ensure all above requirements are met
2. Fork [hacs/default](https://github.com/hacs/default)
3. Create a new branch (not master)
4. Add entry to `integration` file (alphabetically sorted):
   ```json
   "salihinsaealal/home-assistant-tnb-calculator"
   ```
5. Submit PR to hacs/default
6. Fill out PR template completely

**Note**: Integration can be used via HACS custom repository without being in the default store.

## 🎯 Using as Custom Repository (Available Now)

Users can add your integration immediately as a custom repository:

1. In Home Assistant, go to HACS > Integrations
2. Click three dots menu > Custom repositories
3. Add: `https://github.com/salihinsaealal/home-assistant-tnb-calculator`
4. Category: Integration
5. Click Add

## ⚠️ Important Notes

- **HACS Action must pass** before creating a release
- **Create a Release, not just a tag** - Releases are required
- Repository must be **public** on GitHub
- You must be the **owner or major contributor** to submit to default store
- Keep repository **active** (not archived)

## 📚 References

- [HACS General Requirements](https://hacs.xyz/docs/publish/start/)
- [HACS Default Store Inclusion](https://hacs.xyz/docs/publish/include/)
- [Home Assistant Integration Manifest](https://developers.home-assistant.io/docs/creating_integration_manifest)

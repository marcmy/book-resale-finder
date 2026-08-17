# Sourcing Cockpit

A local-first Firefox/Chrome/Edge sourcing companion for Amazon + Keepa.

This project deliberately does **not** copy SourceLens code, assets, guides, or proprietary scoring logic. It recreates useful workflow pieces using public page integration, local storage, and Amazon's official Selling Partner API (SP-API).

## Implemented

- Keepa row ASIN discovery with inline eligibility badges
- Live seller-specific eligibility via SP-API Listings Restrictions
- Approval-required links when Amazon supplies them
- Eligibility cache with manual clear and configurable TTL
- Local gating database generated from observed products
- Bookmarks / Watch Later
- Per-ASIN notes
- Sourcing history + CSV export
- Bulk ASIN cost CSV import/export
- Local deal score heuristic
- Competition trend from locally observed seller-count changes
- Heuristic meltable / hazmat flags
- Similar-product / rabbit-trail search helpers
- Amazon product-page panel
- Optional SP-API fee estimate lookup
- US / Canada / UK marketplace-aware Amazon links, Keepa links and fee currencies
- Pomodoro sourcing timer
- Optional team sync through a GitHub Gist
- Firefox + Chromium Manifest V3 background support

## Normal Windows setup — intended for Doug

The packaged build is designed so the user does **not** need Python, PowerShell, Node, a terminal, JSON editing, or `about:debugging`.

1. Run `SourcingCockpit-Setup-0.2.0.exe`.
2. Leave **Start Sourcing Cockpit automatically when I sign in** enabled.
3. The setup window opens. Paste the four values from the seller's private Amazon SP-API app:
   - Client ID
   - Client secret
   - Refresh token
   - Seller ID
4. Click **Save & connect**. The helper verifies Login with Amazon authorization and then stays in the Windows notification area.
5. If the build contains a Mozilla-signed `SourcingCockpit.xpi`, install it in Firefox and accept Firefox's normal add-on prompt.
6. Open Keepa and use it normally.

After first setup the helper starts automatically with Windows and runs the Amazon bridge on localhost. The user does not need to manually start anything.

### The one unavoidable Amazon step

For a private SP-API application Amazon requires self-authorization. The helper deliberately does not attempt to automate or bypass Amazon's developer authorization process. Once Amazon has issued the values above, they are entered once through the GUI.

The private app needs the **Product Listing** role for seller-specific Listings Restrictions checks. If the optional fee estimator will be used, also grant the **Pricing** role required by Amazon's Product Fees workflow.

### Firefox signing

Release/Beta Firefox requires Mozilla signing for normally installed extensions. The build workflow can sign an unlisted XPI automatically when repository secrets `AMO_JWT_ISSUER` and `AMO_JWT_SECRET` are configured. Without those secrets CI still builds the standalone Windows helper, installer, and an unsigned extension source package for development.

### Windows signing

The current Windows installer/helper are not Authenticode-signed. Windows SmartScreen may therefore display an unknown-publisher warning on a fresh download. That is a packaging/reputation issue rather than an application dependency; removing the warning cleanly requires a Windows code-signing certificate and signing step.

## Security model

- The Amazon client secret and refresh token are stored through Windows Credential Manager using `keyring`.
- Non-secret Amazon settings live under `%LOCALAPPDATA%\SourcingCockpit`.
- The helper binds the SP-API bridge to `127.0.0.1` only.
- The bridge rejects ordinary website origins and browser CORS preflights so random web pages cannot spend the seller's Amazon API quota through localhost.
- POST endpoints require JSON request bodies and do not return raw Amazon error payloads.
- Amazon secrets are never stored in the browser extension or committed to git.
- Gist synchronization is optional and disabled by default. Firefox requests its additional data-collection permissions only if the user enables the feature, and Gist traffic is refused if that consent is later removed.
- Eligibility/storage writes are serialized so concurrent Keepa scans do not silently overwrite one another's cache/history/gating updates.

## Developer layout

- `extension/` — cross-browser Manifest V3 extension
- `bridge/` — localhost SP-API implementation
- `helper.py` — Windows GUI/tray wrapper around the bridge
- `SourcingCockpitHelper.spec` — one-file PyInstaller build
- `installer/` — Inno Setup installer

For direct bridge development, copy `bridge/config.example.json` to `bridge/config.json` and run:

```powershell
py -3.12 .\sourcing_cockpit\bridge\server.py --config .\sourcing_cockpit\bridge\config.json
```

The developer config file is ignored by git. End users should use the packaged helper instead.

## Build

`.github/workflows/sourcing-cockpit-build.yml` validates the Python and JavaScript, runs bridge unit tests, builds `SourcingCockpitHelper.exe`, smoke-tests the frozen executable, stages/lints/packages the Firefox extension, optionally obtains an unlisted Mozilla signature, builds the per-user Windows installer, and uploads the resulting artifacts.

## Known limits

SourceLens also advertises features that depend on proprietary logic, undocumented page integrations, or data we cannot faithfully derive from the public page alone — notably regional Buy Box sweeps and its exact Keepa chart break-even overlay. Those are intentionally not faked here.

DOM extraction is defensive rather than coupled to one Keepa build, but Keepa can still change its markup. The final acceptance test therefore still needs a live Keepa page and the seller's authorized Amazon account; CI can verify packaging and application logic but cannot prove third-party DOM/account integration without those real services.

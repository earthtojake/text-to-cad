# Risky Area: Updater And Packaging

## Main Files

- `src/main/core/updates/update-service.ts`
- `src/main/core/updates/controller.ts`
- `build/`
- `package.json`
- `electron-builder.config.ts`
- `electron-builder.canary.config.ts`
- `scripts/release/build.ts`
- `scripts/release/notarize-mac.ts`
- `scripts/release/rebuild-native.ts`
- `scripts/release/finalize-release.ts`
- `.github/workflows/release-prod.yml`
- `.github/workflows/release-canary.yml`

## Rules

- avoid changing updater defaults casually
- treat signing, notarization, packaging targets, and native rebuild flow as release-critical
- keep build output directories and packaging config stable unless the task is explicitly about release behavior

- A build whose feed answers 404, 403, or is unreachable (a fork, a private repository, an offline
  machine) is not an error state: `update-service.ts` warns once, marks the feed unavailable, and stops
  the hourly schedule for the session. Manual checks from Settings still run.

## Update Feed / Publishing Strategy

The stable release pipeline publishes to **GitHub Releases** (primary feed) and **Cloudflare R2** (legacy/migration feed) in parallel. Both feeds are served from the same single build.

### Two feeds, one build

electron-builder emits channel manifests named by the **first** publish provider's `channel`:

- Stable: `provider: github` has no explicit channel → defaults to `latest` → emits `latest*.yml`.
- Canary: `provider: github` sets `channel: 'canary'` → emits `canary*.yml`.

The R2 feed uses different channel names (`v1-stable`, `v1-canary`) that pre-date the GitHub migration. Rather than running a second packaging pass, `scripts/release/build.ts` calls `duplicateChannelManifests()` after the electron-builder step to copy `latest*.yml → v1-stable*.yml` (or `canary*.yml → v1-canary*.yml`). The duplicated manifests are then uploaded to both the GitHub draft release and R2, so every client cohort sees a consistent manifest for its feed.

### Guard: `upload-r2.ts` hard-fails on missing channel manifest

`scripts/release/upload-r2.ts` asserts that at least one `${channel}*.yml` file exists before uploading. If `duplicateChannelManifests` did not run or produced no output, the R2 upload step fails immediately with a clear message rather than silently uploading only binaries. A stale channel manifest (frozen at a previous version) combined with newer binaries would cause sha512 checksum failures on client download.

### Update channels on GitHub

The app does **not** override `autoUpdater.channel`; the GitHub provider resolves the channel naturally:

- **Stable** (`allowPrerelease=false`): resolves to `latest`, fetches `latest*.yml` from the newest non-prerelease GitHub release.
- **Canary** (`allowPrerelease=true`): resolves the target release tag from the Atom feed by matching the semver prerelease identifier of the installed version (`canary`) against each entry. Once a `-canary.N` tag is found it fetches `canary*.yml` from that release, as defined by `channel: 'canary'` in `electron-builder.canary.config.ts`.

The `UPDATE_CHANNEL` / `v1-stable` / `v1-canary` naming applies **only** to the flat R2 bucket (via the `generic` publish block's `channel`). It is kept as a log label in `update-service.ts` for diagnostics but is not passed to `autoUpdater.channel`.

### R2 decommission path

R2 uploads continue until telemetry confirms all clients have migrated to the GitHub-backed feed. At that point:

1. Remove the `provider: generic` block from `electron-builder.config.ts` and `electron-builder.canary.config.ts`.
2. Remove the `upload-r2.ts` call and `duplicateChannelManifests` call from `build.ts`.
3. Decommission the R2 bucket.

- Canary publishes to GitHub as prereleases. `ALLOW_PRERELEASE` in `update-service.ts` is driven by `IS_CANARY` so canary clients accept prerelease versions automatically.
- The `finalize-release.ts` script runs after all three platform builds complete to flip the draft GitHub release to published. Until that job finishes the release remains a draft and is invisible to electron-updater clients on the GitHub feed.

## Release Scripts Library Usage

- `scripts/release/build.ts` — uses `electron-builder`'s programmatic `build()` API (no CLI spawn)
- `scripts/release/rebuild-native.ts` — uses `@electron/rebuild`'s `rebuild()` API (no CLI spawn)
- `scripts/release/notarize-mac.ts` — uses `@electron/notarize`'s `notarize()` API for DMG submission + auto-staple; system spawns are kept only for `.app` bundle stapling and Gatekeeper verification

## Current Notes

- macOS and Linux release jobs rebuild native modules for the target Electron version
- changelog and auto-update behavior are separate but related surfaces in the app
- the `finalize-release` CI job requires `contents: write` permission and the default `GITHUB_TOKEN`

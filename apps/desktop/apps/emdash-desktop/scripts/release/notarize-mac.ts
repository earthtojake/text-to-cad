import { existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { notarize } from '@electron/notarize';
import { RELEASE_DIR } from './lib/config.ts';
import { exec } from './lib/exec.ts';
import { fail, info, step, warn } from './lib/log.ts';

if (process.platform !== 'darwin') {
  console.log('Not macOS — skipping notarization.');
  process.exit(0);
}

const { values } = parseArgs({
  options: {
    'app-bundle': { type: 'string' },
  },
  strict: true,
});

if (!values['app-bundle']) {
  fail('--app-bundle is required (e.g. --app-bundle "Hardcore.app")');
}

const appBundle = values['app-bundle'];

const apiKeyContent = process.env.APPLE_API_KEY ?? process.env.APPLE_API_KEY_CONTENT;
const apiKeyId = process.env.APPLE_API_KEY_ID;
const apiIssuer = process.env.APPLE_API_ISSUER;

if (!apiKeyContent || !apiKeyId || !apiIssuer) {
  warn('Apple API key not configured; skipping notarization.');
  process.exit(0);
}

// If the env var carries the key content inline (not a file path), write it to a temp file
let keyFile = apiKeyContent;
if (apiKeyContent.includes('BEGIN PRIVATE KEY') || apiKeyContent.length > 500) {
  keyFile = join(tmpdir(), `apple_api_key_${Date.now()}.p8`);
  writeFileSync(keyFile, apiKeyContent);
}

// Absolute paths: @electron/notarize resolves .dmg/.pkg appPath against an internal
// temp dir, so a relative path would be looked up under that temp dir and fail.
const dmgs = readdirSync(RELEASE_DIR)
  .filter((f) => f.endsWith('.dmg'))
  .map((f) => resolve(RELEASE_DIR, f));

if (dmgs.length === 0) {
  warn('No DMG files found — nothing to notarize.');
  process.exit(0);
}

// Notarize and auto-staple each DMG via @electron/notarize (submits to notarytool, then staples)
for (const dmg of dmgs) {
  step(`Notarizing ${dmg}`);
  await notarize({
    tool: 'notarytool',
    appPath: dmg,
    appleApiKey: keyFile,
    appleApiKeyId: apiKeyId,
    appleApiIssuer: apiIssuer,
  });
  info(`Notarized and stapled: ${dmg}`);
  exec(`xcrun stapler validate "${dmg}"`, { echo: true });
}

// Staple app bundles inside release output dirs
step('Staple app bundles');
const macDirs = readdirSync(RELEASE_DIR)
  .filter((d) => d.startsWith('mac'))
  .map((d) => join(RELEASE_DIR, d, appBundle))
  .filter((p) => existsSync(p));

for (const appDir of macDirs) {
  info(`Stapling ${appDir}`);
  try {
    exec(`xcrun stapler staple "${appDir}"`, { echo: true });
    exec(`xcrun stapler validate "${appDir}"`, { echo: true });
  } catch {
    warn(`App staple failed for ${appDir} (may not be individually notarized)`);
  }
}

step('Gatekeeper check (app inside DMG)');
for (const dmg of dmgs) {
  const mnt = mkdtempSync(join(tmpdir(), 'dmg-'));
  try {
    exec(`hdiutil attach "${dmg}" -mountpoint "${mnt}" -nobrowse -quiet`, { echo: true });
    const appPath = join(mnt, appBundle);
    if (!existsSync(appPath)) {
      fail(`No ${appBundle} found inside ${dmg}`);
    }
    exec(`spctl -a -vv --type execute "${appPath}"`, { echo: true });
    info(`Gatekeeper passed for ${dmg}`);
  } finally {
    try {
      exec(`hdiutil detach "${mnt}" -quiet`);
    } catch {
      /* best effort */
    }
    rmSync(mnt, { recursive: true, force: true });
  }
}

import { existsSync, readdirSync } from 'node:fs';
import { basename, join } from 'node:path';
import { parseArgs } from 'node:util';
import { RELEASE_DIR } from './lib/config.ts';
import { exec, execOrNull } from './lib/exec.ts';
import { fail, info, step } from './lib/log.ts';

if (process.platform !== 'darwin') {
  console.log('Not macOS — skipping verification.');
  process.exit(0);
}

const { values } = parseArgs({
  options: {
    'expected-team-id': { type: 'string' },
  },
  strict: true,
});

const expectedTeamId = values['expected-team-id'];

const appBundles = readdirSync(RELEASE_DIR)
  .filter((d) => d.startsWith('mac'))
  .flatMap((d) => {
    const dir = join(RELEASE_DIR, d);
    return readdirSync(dir)
      .filter((f) => f.endsWith('.app'))
      .map((f) => join(dir, f));
  })
  .filter((p) => existsSync(p));

if (appBundles.length === 0) {
  fail('No app bundles found to verify');
}

let verified = 0;

for (const appDir of appBundles) {
  const archDir = appDir.split('/').at(-2)!;
  const expectedArch =
    archDir === 'mac-arm64' ? 'arm64' : archDir.startsWith('mac') ? 'x86_64' : null;

  const productName = basename(appDir, '.app');

  step(`Verifying ${appDir} (expected: ${expectedArch ?? 'unknown'})`);

  const electronBin = join(appDir, 'Contents', 'MacOS', productName);
  const sqliteNode = join(
    appDir,
    'Contents',
    'Resources',
    'app.asar.unpacked',
    'node_modules',
    'better-sqlite3',
    'build',
    'Release',
    'better_sqlite3.node'
  );

  if (expectedArch) {
    const binArch = execOrNull(`file "${electronBin}" | grep -o 'arm64\\|x86_64' | head -1`);
    info(`Electron binary: ${binArch}`);
    if (binArch !== expectedArch) {
      fail(`Electron arch mismatch: got ${binArch}, expected ${expectedArch}`);
    }

    if (!existsSync(sqliteNode)) {
      fail(`better-sqlite3 native module not found at ${sqliteNode}`);
    }
    const sqliteArch = execOrNull(`file "${sqliteNode}" | grep -o 'arm64\\|x86_64' | head -1`);
    info(`better-sqlite3 native module: ${sqliteArch}`);
    if (sqliteArch !== expectedArch) {
      fail(`better-sqlite3 arch mismatch: got ${sqliteArch}, expected ${expectedArch}`);
    }
  }

  const plist = join(appDir, 'Contents', 'Info.plist');
  if (existsSync(plist)) {
    const bid =
      execOrNull(`/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "${plist}"`) ??
      execOrNull(
        `plutil -extract CFBundleIdentifier xml1 -o - "${plist}" | sed -n 's/.*<string>\\(.*\\)<\\/string>.*/\\1/p' | head -n1`
      );
    info(`CFBundleIdentifier: ${bid}`);
  }

  exec(`codesign --verify --deep --strict --verbose=2 "${appDir}"`, { echo: true });

  if (expectedTeamId) {
    const meta = exec(`codesign -dv --verbose=4 "${appDir}" 2>&1`);
    if (!meta.includes('Authority=Developer ID Application')) {
      fail('Not Developer ID Application signed');
    }
    const tidMatch = meta.match(/TeamIdentifier=(\S+)/);
    const tid = tidMatch?.[1];
    if (tid !== expectedTeamId) {
      fail(`TeamIdentifier mismatch (got '${tid}', expected '${expectedTeamId}')`);
    }
    info(`TeamIdentifier: ${tid}`);
  }

  verified++;
}

info(`Verified ${verified} app bundle(s)`);

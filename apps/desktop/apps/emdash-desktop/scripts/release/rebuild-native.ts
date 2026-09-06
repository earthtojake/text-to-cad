import { cwd } from 'node:process';
import { parseArgs } from 'node:util';
import { rebuild } from '@electron/rebuild';
import { NATIVE_MODULES } from './lib/config.ts';
import { exec } from './lib/exec.ts';
import { fail, info, step } from './lib/log.ts';

const { values } = parseArgs({
  options: {
    arch: { type: 'string' },
    'deploy-dir': { type: 'string' },
  },
  strict: true,
});

const arch = values.arch;
if (!arch || !['arm64', 'x64'].includes(arch)) {
  fail('Usage: rebuild-native.ts --arch arm64|x64 [--deploy-dir <path>]');
}

const deployDir = values['deploy-dir'];
const buildPath = deployDir ?? cwd();

const electronVersion = exec('node -p "require(\'electron/package.json\').version"');
step(`Rebuilding native modules for ${arch} (Electron ${electronVersion})`);

await rebuild({
  buildPath,
  electronVersion,
  arch,
  onlyModules: NATIVE_MODULES,
  force: true,
  buildFromSource: true,
});

info(`Native modules rebuilt for ${arch}`);

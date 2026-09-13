import { readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { releaseMetadataOutput, type ReleaseChannel } from './package-helpers.ts';

const appDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');

async function main(): Promise<void> {
  const [channelValue, runNumberValue, extra] = process.argv.slice(2);
  if (channelValue === undefined || runNumberValue === undefined || extra !== undefined) {
    throw new Error('Usage: print-release-metadata.ts <stable|canary> <run-number>');
  }
  const channel = parseReleaseChannel(channelValue);
  const runNumber = Number(runNumberValue);
  if (!Number.isSafeInteger(runNumber) || runNumber <= 0 || String(runNumber) !== runNumberValue) {
    throw new Error(`Invalid release run number '${runNumberValue}'`);
  }

  const raw: unknown = JSON.parse(await readFile(join(appDirectory, 'package.json'), 'utf8'));
  if (!isRecord(raw) || typeof raw['version'] !== 'string') {
    throw new Error('workspace-server package.json must contain a string version');
  }
  process.stdout.write(releaseMetadataOutput(channel, raw['version'], runNumber));
}

function parseReleaseChannel(value: string): ReleaseChannel {
  if (value === 'stable' || value === 'canary') return value;
  throw new Error(`Invalid workspace-server release channel '${value}'`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

void main().catch((error: unknown) => {
  process.stderr.write(
    `workspace-server release metadata failed: ${error instanceof Error ? error.message : String(error)}\n`
  );
  process.exit(1);
});

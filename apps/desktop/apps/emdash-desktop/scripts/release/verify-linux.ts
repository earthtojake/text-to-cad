import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fail, info } from './lib/log.ts';

const DEFAULT_MAX_GLIBC = '2.35';
const RELEASE_DIR = 'release';
const maxGlibc = process.env.EMDASH_MAX_GLIBC ?? DEFAULT_MAX_GLIBC;

interface GlibcSymbol {
  file: string;
  version: string;
}

function parseVersion(version: string): [number, number] {
  const match = /^(\d+)\.(\d+)$/.exec(version);
  if (!match) fail(`Invalid GLIBC version: ${version}`);
  return [Number(match[1]), Number(match[2])];
}

function isGreaterVersion(actual: string, max: string): boolean {
  const [actualMajor, actualMinor] = parseVersion(actual);
  const [maxMajor, maxMinor] = parseVersion(max);
  return actualMajor > maxMajor || (actualMajor === maxMajor && actualMinor > maxMinor);
}

function findNativeModules(dir: string): string[] {
  const results: string[] = [];

  for (const entry of readdirSync(dir)) {
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath);

    if (stat.isDirectory()) {
      results.push(...findNativeModules(fullPath));
      continue;
    }

    if (
      entry.endsWith('.node') &&
      !fullPath.includes('/darwin-') &&
      !fullPath.includes('/win32-')
    ) {
      results.push(fullPath);
    }
  }

  return results;
}

interface GlibcInspection {
  file: string;
  symbols: string[];
  error?: string;
}

function inspectGlibcSymbols(file: string): GlibcInspection {
  try {
    const output = execFileSync('objdump', ['-T', file], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return {
      file,
      symbols: Array.from(output.matchAll(/GLIBC_(\d+\.\d+)/g), (match) => match[1]),
    };
  } catch (error) {
    return {
      file,
      symbols: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

if (!existsSync(RELEASE_DIR)) {
  fail(`Cannot verify Linux native modules because ${RELEASE_DIR}/ does not exist`);
}

const nativeModules = findNativeModules(RELEASE_DIR);
if (nativeModules.length === 0) {
  fail(`Cannot verify Linux native modules because no .node files were found in ${RELEASE_DIR}/`);
}

const violations: GlibcSymbol[] = [];
const inspectionFailures: GlibcInspection[] = [];
let inspected = 0;

for (const file of nativeModules) {
  const inspection = inspectGlibcSymbols(file);
  if (inspection.error) {
    inspectionFailures.push(inspection);
    continue;
  }

  const { symbols } = inspection;
  if (symbols.length === 0) continue;

  inspected += 1;
  for (const version of new Set(symbols)) {
    if (isGreaterVersion(version, maxGlibc)) {
      violations.push({ file, version });
    }
  }
}

if (inspectionFailures.length > 0) {
  const details = inspectionFailures.map(({ file, error }) => `  ${file}: ${error}`).join('\n');
  fail(`Cannot verify Linux native modules because objdump failed for:\n${details}`);
}

if (inspected === 0) {
  fail('Cannot verify Linux native modules because objdump found no GLIBC symbols');
}

if (violations.length > 0) {
  const details = violations.map(({ file, version }) => `  ${file}: GLIBC_${version}`).join('\n');
  fail(`Linux native modules require GLIBC newer than ${maxGlibc}:\n${details}`);
}

info(`Verified ${inspected} Linux native module(s) against GLIBC <= ${maxGlibc}`);

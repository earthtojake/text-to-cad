import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { app } from 'electron';
import { log } from '@main/lib/logger';
import { getAppConfig, type AppConfig } from './config';

type BootState = {
  booting: boolean;
  failures: number;
};

const EMPTY_BOOT_STATE: BootState = { booting: false, failures: 0 };
const BOOT_STATE_FILENAME = 'boot-state.json';
let quitCleanupRegistered = false;

export function observePreviousBoot(config: AppConfig): BootState {
  if (config.isDev) return EMPTY_BOOT_STATE;

  const state = readBootState();
  if (!state.booting) return state;

  const observed = {
    booting: false,
    failures: state.failures + 1,
  };
  writeBootState(observed);
  return observed;
}

export function writeBootingMarker(config: AppConfig): void {
  if (config.isDev) return;
  const state = readBootState();
  writeBootState({ booting: true, failures: state.failures });
  registerQuitCleanup();
}

export function markBootSuccessful(): void {
  const config = getAppConfig();
  if (config.isDev) return;
  clearBootFailureMarker();
}

/**
 * Converts the in-progress booting marker into a counted failure at the moment
 * the backend fails. Without this eager write, the failure would only be
 * counted if the process died uncleanly: quitting the recovery window fires
 * the quit cleanup, and an unguarded cleanup would erase the evidence the
 * crash-loop guard needs to open recovery instead of the main window.
 */
export function recordBootFailure(config: AppConfig): void {
  if (config.isDev) return;
  const state = readBootState();
  writeBootState({ booting: false, failures: state.failures + 1 });
}

/**
 * Quit-time cleanup: a quit while boot is still in progress is a user abort,
 * not a failure, so the marker is cleared. A recorded failure
 * (`booting: false`, `failures > 0`) must survive the quit so consecutive
 * failures are counted across launches.
 */
export function clearBootMarkerIfStillBooting(): void {
  if (readBootState().booting) clearBootFailureMarker();
}

export function clearBootFailureMarker(): void {
  try {
    rmSync(bootStatePath(), { force: true });
  } catch (error) {
    log.warn('Failed to clear boot failure marker', { error });
  }
}

function readBootState(): BootState {
  try {
    const parsed = JSON.parse(readFileSync(bootStatePath(), 'utf8')) as {
      booting?: unknown;
      failures?: unknown;
    };
    if (typeof parsed.booting !== 'boolean' || typeof parsed.failures !== 'number') {
      return EMPTY_BOOT_STATE;
    }
    return {
      booting: parsed.booting,
      failures: Math.max(0, Math.trunc(parsed.failures)),
    };
  } catch (error) {
    if (isMissingFileError(error)) return EMPTY_BOOT_STATE;
    log.warn('Failed to read boot failure marker', { error });
    return EMPTY_BOOT_STATE;
  }
}

function registerQuitCleanup(): void {
  if (quitCleanupRegistered) return;
  quitCleanupRegistered = true;
  app.once('before-quit', clearBootMarkerIfStillBooting);
}

function writeBootState(state: BootState): void {
  const path = bootStatePath();
  const temporaryPath = `${path}.${process.pid}.tmp`;
  try {
    mkdirSync(app.getPath('userData'), { recursive: true });
    writeFileSync(temporaryPath, JSON.stringify(state), { encoding: 'utf8', mode: 0o600 });
    replaceFile(temporaryPath, path);
  } catch (error) {
    try {
      rmSync(temporaryPath, { force: true });
    } catch {
      // Best effort only.
    }
    log.warn('Failed to write boot failure marker', { error });
  }
}

function replaceFile(temporaryPath: string, path: string): void {
  try {
    renameSync(temporaryPath, path);
  } catch (error) {
    if (!isReplaceConflict(error)) throw error;
    // Windows does not consistently allow rename-over-existing. Preserve the
    // atomic path on other platforms and use the smallest possible gap here.
    rmSync(path, { force: true });
    renameSync(temporaryPath, path);
  }
}

function bootStatePath(): string {
  return join(app.getPath('userData'), BOOT_STATE_FILENAME);
}

function isReplaceConflict(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    ['EEXIST', 'EPERM', 'EACCES'].includes((error as NodeJS.ErrnoException).code ?? '')
  );
}

function isMissingFileError(error: unknown): boolean {
  return (
    error instanceof Error && 'code' in error && (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}

import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadAppConfig } from './config';

describe('loadAppConfig', () => {
  it('uses the documented defaults', () => {
    const config = loadAppConfig({});

    expect(config.dbFile).toBeUndefined();
    expect(config.disableNativeDb).toBe(false);
    expect(config.telemetryEnabled).toBe(true);
    expect(config.installSource).toBeUndefined();
    expect(config.forceBootFailure).toBe(false);
  });

  it('maps runtime environment variables', () => {
    const config = loadAppConfig({
      EMDASH_DB_FILE: ' ./test.db ',
      EMDASH_DISABLE_NATIVE_DB: '1',
      TELEMETRY_ENABLED: 'false',
      INSTALL_SOURCE: 'managed',
      EMDASH_FORCE_BOOT_FAILURE: '1',
    });

    expect(config.dbFile).toBe('./test.db');
    expect(config.disableNativeDb).toBe(true);
    expect(config.telemetryEnabled).toBe(false);
    expect(config.installSource).toBe('managed');
    expect(config.forceBootFailure).toBe(true);
  });

  it.each(['false', '0', 'no', 'NO'])('disables telemetry for %s', (value) => {
    expect(loadAppConfig({ TELEMETRY_ENABLED: value }).telemetryEnabled).toBe(false);
  });

  it('only disables the native database for the value 1', () => {
    expect(loadAppConfig({ EMDASH_DISABLE_NATIVE_DB: 'true' }).disableNativeDb).toBe(false);
    expect(loadAppConfig({ EMDASH_DISABLE_NATIVE_DB: '0' }).disableNativeDb).toBe(false);
    expect(loadAppConfig({ EMDASH_DISABLE_NATIVE_DB: '1' }).disableNativeDb).toBe(true);
  });

  it('rejects an empty explicit database path', () => {
    expect(() => loadAppConfig({ EMDASH_DB_FILE: ' ' })).toThrow(
      'emdashDbFile: Database path cannot be empty'
    );
  });
});

describe('userData configuration guard', () => {
  const processWithType = process as NodeJS.Process & { type?: string };
  const originalElectron = Object.getOwnPropertyDescriptor(process.versions, 'electron');
  const originalType = Object.getOwnPropertyDescriptor(processWithType, 'type');

  afterEach(() => {
    vi.resetModules();
    if (originalElectron) {
      Object.defineProperty(process.versions, 'electron', originalElectron);
    } else {
      Reflect.deleteProperty(process.versions, 'electron');
    }
    if (originalType) {
      Object.defineProperty(processWithType, 'type', originalType);
    } else {
      Reflect.deleteProperty(processWithType, 'type');
    }
  });

  it('fails before userData configuration and succeeds afterward', async () => {
    Object.defineProperty(process.versions, 'electron', {
      configurable: true,
      value: 'test',
    });
    Object.defineProperty(processWithType, 'type', {
      configurable: true,
      value: 'browser',
    });
    const { assertUserDataConfigured, markUserDataConfigured } = await import('./config');

    expect(() => assertUserDataConfigured()).toThrow(
      'The database path was resolved before the Electron userData path was configured.'
    );
    markUserDataConfigured();
    expect(() => assertUserDataConfigured()).not.toThrow();
  });
});

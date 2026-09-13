import { describe, expect, it } from 'vitest';
import {
  checkEscapeHatches,
  checkPinnedVersion,
  classifyElectronAbiProbe,
  formatReport,
  overallExitCode,
  parsePnpmVersion,
} from './doctor-checks.ts';

describe('checkPinnedVersion', () => {
  it('is ok when the actual version matches the pin', () => {
    const result = checkPinnedVersion('node', '24.14.0', '24.14.0');
    expect(result.status).toBe('ok');
  });

  it('fails with an actionable line on mismatch', () => {
    const result = checkPinnedVersion('node', '22.1.0', '24.14.0');
    expect(result.status).toBe('fail');
    expect(result.detail).toContain('22.1.0');
    expect(result.detail).toContain('24.14.0');
    expect(result.fix).toContain('pnpm install');
  });

  it('fails when the actual version is unknown', () => {
    const result = checkPinnedVersion('pnpm', undefined, '10.28.2');
    expect(result.status).toBe('fail');
  });
});

describe('parsePnpmVersion', () => {
  it('extracts the pnpm version from npm_config_user_agent', () => {
    expect(parsePnpmVersion('pnpm/10.28.2 npm/? node/v24.14.0 darwin arm64')).toBe('10.28.2');
  });

  it('returns undefined for non-pnpm agents or missing values', () => {
    expect(parsePnpmVersion('npm/10.9.0 node/v22.0.0')).toBeUndefined();
    expect(parsePnpmVersion(undefined)).toBeUndefined();
  });
});

describe('classifyElectronAbiProbe', () => {
  const expectedElectronAbi = '143';

  it('treats an ABI mismatch citing the Electron ABI as correctly built', () => {
    const result = classifyElectronAbiProbe({
      loaded: false,
      errorMessage:
        'The module was compiled against a different Node.js version using NODE_MODULE_VERSION 143. This version of Node.js requires NODE_MODULE_VERSION 137.',
      expectedElectronAbi,
    });
    expect(result.status).toBe('ok');
  });

  it('flags a copy that loads under system Node as wrongly built', () => {
    const result = classifyElectronAbiProbe({ loaded: true, expectedElectronAbi });
    expect(result.status).toBe('fail');
    expect(result.fix).toContain('pnpm run rebuild');
  });

  it('flags a copy citing a different ABI as stale', () => {
    const result = classifyElectronAbiProbe({
      loaded: false,
      errorMessage: 'NODE_MODULE_VERSION 140. This version of Node.js requires 137.',
      expectedElectronAbi,
    });
    expect(result.status).toBe('fail');
  });

  it('flags a missing build', () => {
    const result = classifyElectronAbiProbe({
      loaded: false,
      errorMessage: "Cannot find module 'better-sqlite3'",
      expectedElectronAbi,
    });
    expect(result.status).toBe('fail');
    expect(result.fix).toBeDefined();
  });
});

describe('checkEscapeHatches', () => {
  it('reports no active hatches on a clean env', () => {
    const result = checkEscapeHatches({});
    expect(result.status).toBe('ok');
  });

  it('surfaces every active hatch by name', () => {
    const result = checkEscapeHatches({
      EMDASH_DB_FILE: '/tmp/x.db',
      EMDASH_DISABLE_PTY: '1',
      HOME: '/Users/dev',
    });
    expect(result.status).toBe('warn');
    expect(result.detail).toContain('EMDASH_DB_FILE');
    expect(result.detail).toContain('EMDASH_DISABLE_PTY');
    expect(result.detail).not.toContain('HOME');
  });
});

describe('formatReport and overallExitCode', () => {
  it('renders one line per check and fix lines for failures', () => {
    const report = formatReport([
      { name: 'node version', status: 'ok', detail: '24.14.0' },
      {
        name: 'playwright',
        status: 'fail',
        detail: 'missing',
        fix: 'pnpm exec playwright install',
      },
    ]);
    expect(report).toContain('node version');
    expect(report).toContain('pnpm exec playwright install');
  });

  it('exits non-zero only when a check failed', () => {
    expect(overallExitCode([{ name: 'a', status: 'ok', detail: '' }])).toBe(0);
    expect(
      overallExitCode([
        { name: 'a', status: 'ok', detail: '' },
        { name: 'b', status: 'warn', detail: '' },
        { name: 'c', status: 'info', detail: '' },
      ])
    ).toBe(0);
    expect(overallExitCode([{ name: 'a', status: 'fail', detail: '' }])).toBe(1);
  });
});

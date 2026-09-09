/**
 * Pure check logic for `pnpm run doctor`. Every function here is
 * side-effect-free so the report shapes stay unit-testable; the IO probes
 * live in scripts/doctor.ts.
 */

export type CheckStatus = 'ok' | 'warn' | 'fail' | 'info';

export type CheckResult = {
  name: string;
  status: CheckStatus;
  detail: string;
  /** The command that fixes the problem; printed for every failing line. */
  fix?: string;
};

export function checkPinnedVersion(
  kind: 'node' | 'pnpm',
  actual: string | undefined,
  pinned: string
): CheckResult {
  const name = `${kind} version`;
  if (!actual) {
    return {
      name,
      status: 'fail',
      detail: `could not determine the running ${kind} version (pin: ${pinned})`,
      fix: 'pnpm install',
    };
  }
  if (actual === pinned) {
    return { name, status: 'ok', detail: `${actual} (matches the package.json pin)` };
  }
  return {
    name,
    status: 'fail',
    detail: `running ${actual} but package.json pins ${pinned}`,
    fix: 'pnpm install  (pnpm provisions the pinned toolchain itself)',
  };
}

/** npm_config_user_agent looks like "pnpm/10.28.2 npm/? node/v24.14.0 darwin arm64". */
export function parsePnpmVersion(userAgent: string | undefined): string | undefined {
  const match = userAgent?.match(/\bpnpm\/(\S+)/);
  return match?.[1];
}

export type ElectronAbiProbe = {
  /** Whether the app copy of better-sqlite3 loaded under the current (system-Node) runtime. */
  loaded: boolean;
  errorMessage?: string;
  expectedElectronAbi: string;
};

/**
 * Classifies the app's better-sqlite3 copy. An Electron-ABI binary cannot be
 * loaded from system Node, so the probe is indirect: a dlopen failure whose
 * NODE_MODULE_VERSION matches the installed Electron's ABI proves the copy is
 * correctly Electron-built; a clean load proves it was (wrongly) built for
 * system Node; anything else means missing or stale.
 */
export function classifyElectronAbiProbe(probe: ElectronAbiProbe): CheckResult {
  const name = 'better-sqlite3 (app copy, Electron ABI)';
  if (probe.loaded) {
    return {
      name,
      status: 'fail',
      detail: 'loads under system Node, so it is not built for the Electron ABI',
      fix: 'pnpm run rebuild  (from apps/emdash-desktop)',
    };
  }
  const binaryAbi = probe.errorMessage?.match(/NODE_MODULE_VERSION (\d+)/)?.[1];
  if (binaryAbi === probe.expectedElectronAbi) {
    return {
      name,
      status: 'ok',
      detail: `built for Electron ABI ${probe.expectedElectronAbi} (verified via dlopen ABI probe)`,
    };
  }
  if (binaryAbi) {
    return {
      name,
      status: 'fail',
      detail: `built for ABI ${binaryAbi} but the installed Electron needs ${probe.expectedElectronAbi}`,
      fix: 'pnpm run rebuild  (from apps/emdash-desktop)',
    };
  }
  return {
    name,
    status: 'fail',
    detail: `not loadable: ${probe.errorMessage ?? 'unknown error'}`,
    fix: 'pnpm install  (or pnpm run rebuild from apps/emdash-desktop)',
  };
}

export const ESCAPE_HATCH_VARS = [
  'EMDASH_SKIP_ELECTRON_REBUILD',
  'EMDASH_DISABLE_NATIVE_DB',
  'EMDASH_DISABLE_PTY',
  'EMDASH_DB_FILE',
  'EMDASH_FORCE_BOOT_FAILURE',
  'EMDASH_TEST_SKIP_BROWSER',
  'CODEX_SANDBOX_MODE',
  'CODEX_APPROVAL_POLICY',
  'TELEMETRY_ENABLED',
] as const;

export function checkEscapeHatches(env: Record<string, string | undefined>): CheckResult {
  const active = ESCAPE_HATCH_VARS.filter((name) => env[name] !== undefined && env[name] !== '');
  if (active.length === 0) {
    return { name: 'escape-hatch env vars', status: 'ok', detail: 'none active' };
  }
  return {
    name: 'escape-hatch env vars',
    status: 'warn',
    detail: `active: ${active.map((name) => `${name}=${env[name]}`).join(', ')} — behavior deviates from the default setup`,
  };
}

const STATUS_ICONS: Record<CheckStatus, string> = {
  ok: '✓',
  warn: '!',
  fail: '✗',
  info: '•',
};

export function formatReport(results: CheckResult[]): string {
  const lines: string[] = [];
  for (const result of results) {
    lines.push(`${STATUS_ICONS[result.status]} ${result.name}: ${result.detail}`);
    if (result.fix && result.status === 'fail') {
      lines.push(`    fix: ${result.fix}`);
    }
  }
  return lines.join('\n');
}

export function overallExitCode(results: CheckResult[]): 0 | 1 {
  return results.some((result) => result.status === 'fail') ? 1 : 0;
}

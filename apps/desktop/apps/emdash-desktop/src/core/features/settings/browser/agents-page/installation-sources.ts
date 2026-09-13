import type {
  DependencyStatus,
  HostDependencySelection,
  Installation,
  InstallMethod,
  InstallOption,
  Provenance,
  SelectedSource,
} from '@core/primitives/agents/api';
import { resolveActiveInstallation, sourceKey } from '@core/primitives/agents/api';
import { humanizeMethod } from '@core/primitives/agents/browser/install-command-row';

// Re-export shared SelectedSource as SourceRef for backward compat with callers.
export type { SelectedSource as SourceRef };
export { sourceKey as installIdOf };

export function findInstallation(
  installs: Installation[],
  ref: SelectedSource
): Installation | undefined {
  return resolveActiveInstallation(installs, ref);
}

export function toSelection(
  ref: SelectedSource,
  overrideValues: { path?: string; cli?: string } = {}
): HostDependencySelection {
  if (ref.kind === 'pinned') return { kind: 'pinned', realpath: ref.realpath };
  if (ref.kind === 'path') return { kind: 'path', path: overrideValues.path ?? '' };
  if (ref.kind === 'cli') return { kind: 'cli', command: overrideValues.cli ?? '' };
  if (ref.kind === 'method') return { kind: 'method', method: ref.method };
  // auto → null (clear override)
  return null;
}

export function refLabel(ref: SelectedSource, installOptions: InstallOption[]): string {
  if (ref.kind === 'auto') return 'Auto';
  if (ref.kind === 'pinned') return `Pinned`;
  if (ref.kind === 'path') return 'Path Override';
  if (ref.kind === 'cli') return 'CLI Override';
  const opt = installOptions.find((o) => o.method === ref.method);
  return opt?.label ?? humanizeMethod(ref.method);
}

// ---------------------------------------------------------------------------
// Provenance label helper
// ---------------------------------------------------------------------------

const NON_PM_KINDS = new Set(['manual', 'version-manager', 'unknown']);

export function provenanceLabel(provenance: Provenance): string {
  const { kind } = provenance;
  if (kind === 'manual') return 'Manual';
  if (kind === 'version-manager') return 'Version manager';
  if (kind === 'unknown') return 'Unknown';
  return humanizeMethod(kind as InstallMethod) || kind;
}

// ---------------------------------------------------------------------------
// SourceRow — a flattened entry for the source-switcher menu
// ---------------------------------------------------------------------------

export type SourceRow = {
  ref: SelectedSource;
  label: string;
  status: DependencyStatus | 'missing';
  recommended?: boolean;
  /** Short display path (pathEntry or realpath, truncated). Only for detected rows. */
  displayPath?: string;
};

function shortPath(p: string | null): string | undefined {
  if (!p) return undefined;
  return p.length > 40 ? '…' + p.slice(-37) : p;
}

/**
 * Rows for enumerated discovered installations (from `which -a` enumeration).
 * Each is selectable as { kind: 'pinned', realpath }.
 * Label shows provenance + version + short path.
 */
export function detectedInstallationRows(installations: Installation[]): SourceRow[] {
  return installations
    .filter((i) => i.id !== 'path' && i.id !== 'cli')
    .map((i) => {
      const methodLabel = provenanceLabel(i.provenance);
      const versionPart = i.version ? ` v${i.version}` : '';
      const path = i.pathEntry ?? i.realpath;
      return {
        ref: { kind: 'pinned', realpath: i.realpath } as SelectedSource,
        label: `${methodLabel}${versionPart}`,
        status: i.status,
        displayPath: shortPath(path),
      };
    });
}

/**
 * Rows for install options whose method is NOT already detected on this host.
 * These are "install" recipes, not selectable as a current source.
 */
export function installOptionRows(
  installOptions: InstallOption[],
  installations: Installation[]
): SourceRow[] {
  const detectedKinds = new Set(
    installations.filter((i) => i.id !== 'path' && i.id !== 'cli').map((i) => i.provenance.kind)
  );
  return installOptions
    .filter((o) => !NON_PM_KINDS.has(o.method) && !detectedKinds.has(o.method))
    .map((o) => ({
      ref: { kind: 'method', method: o.method as InstallMethod },
      label: o.label ?? humanizeMethod(o.method as InstallMethod),
      status: 'missing' as const,
      recommended: o.recommended,
    }));
}

/**
 * Builds the full source rows for the source-switcher menu.
 *
 * Order:
 *   1. Auto — follows the current PATH winner
 *   2. Detected installations (real binaries found by `which -a`, selectable as pinned)
 *   3. Install options whose method is not yet detected (install actions)
 *   4. Path override
 *   5. CLI override
 */
export function buildSourceRows(
  installOptions: InstallOption[],
  installations: Installation[]
): SourceRow[] {
  const rows: SourceRow[] = [];

  // 1. Auto row — a policy ("follow the PATH winner"), not a concrete install.
  // It never carries an "Installed" badge; instead the sublabel shows what it
  // currently resolves to so the user can see where auto points.
  const activeInst = installations.find((i) => i.isActive);
  rows.push({
    ref: { kind: 'auto' },
    label: 'Auto',
    status: activeInst?.status ?? 'missing',
    displayPath: activeInst ? shortPath(activeInst.pathEntry ?? activeInst.realpath) : undefined,
  });

  // 2. Detected installations
  rows.push(...detectedInstallationRows(installations));

  // 3. Install options not yet detected
  rows.push(...installOptionRows(installOptions, installations));

  // 4. Path override
  const pathInst = installations.find((i) => i.id === 'path');
  rows.push({
    ref: { kind: 'path', path: pathInst?.pathEntry ?? '' },
    label: 'Path Override',
    status: pathInst?.status ?? 'missing',
  });

  // 5. CLI override
  const cliInst = installations.find((i) => i.id === 'cli');
  rows.push({
    ref: { kind: 'cli', command: cliInst?.pathEntry ?? '' },
    label: 'CLI Override',
    status: cliInst?.status ?? 'missing',
  });

  return rows;
}

/**
 * Derives a SelectedSource from the current `used` value.
 * Falls back to { kind: 'auto' } when undefined.
 */
export function refFromUsed(used: SelectedSource | undefined): SelectedSource {
  return used ?? { kind: 'auto' };
}

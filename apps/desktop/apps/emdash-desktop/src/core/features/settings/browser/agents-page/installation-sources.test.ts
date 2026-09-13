import { describe, expect, it } from 'vitest';
import type {
  Installation,
  InstallOption,
  Provenance,
  SelectedSource,
} from '@core/primitives/agents/api';
import { sourceKey } from '@core/primitives/agents/api';
import {
  buildSourceRows,
  findInstallation,
  refFromUsed,
  toSelection,
} from './installation-sources';

// ---------------------------------------------------------------------------
// Test fixture helpers
// ---------------------------------------------------------------------------

function makeInstall(opts: {
  realpath?: string;
  pathEntry?: string;
  isActive?: boolean;
  manageable?: boolean;
  provenanceKind?: Provenance['kind'];
  provenanceConfidence?: 'confirmed' | 'inferred';
  id?: string;
  status?: 'available' | 'missing';
  version?: string | null;
}): Installation {
  const realpath = opts.realpath ?? '/usr/bin/tool';
  const id = opts.id ?? realpath;
  const status = opts.status ?? 'available';
  return {
    id,
    realpath,
    pathEntry: opts.pathEntry ?? (opts.id ? (opts.realpath ?? realpath) : realpath),
    isActive: opts.isActive ?? false,
    manageable: opts.manageable ?? status === 'available',
    provenance: {
      kind: opts.provenanceKind ?? 'unknown',
      confidence: opts.provenanceConfidence ?? 'inferred',
    },
    status,
    version: opts.version !== undefined ? opts.version : status === 'available' ? '1.0.0' : null,
    latestVersion: null,
    updateAvailable: false,
  };
}

const installOptions: InstallOption[] = [
  { method: 'npm', command: 'npm install -g mytool', recommended: true },
  { method: 'homebrew', command: 'brew install mytool' },
];

// ---------------------------------------------------------------------------
// sourceKey
// ---------------------------------------------------------------------------

describe('sourceKey (installIdOf)', () => {
  it('returns auto for auto', () => expect(sourceKey({ kind: 'auto' })).toBe('auto'));
  it('returns method:<m> for method', () =>
    expect(sourceKey({ kind: 'method', method: 'npm' })).toBe('method:npm'));
  it('returns path for path', () =>
    expect(sourceKey({ kind: 'path', path: '/usr/bin/foo' })).toBe('path'));
  it('returns cli for cli', () => expect(sourceKey({ kind: 'cli', command: 'foo' })).toBe('cli'));
  it('returns realpath for pinned', () =>
    expect(sourceKey({ kind: 'pinned', realpath: '/opt/homebrew/bin/tool' })).toBe(
      '/opt/homebrew/bin/tool'
    ));
});

// ---------------------------------------------------------------------------
// findInstallation (uses resolveActiveInstallation)
// ---------------------------------------------------------------------------

describe('findInstallation', () => {
  const npmInstall = makeInstall({
    realpath: '/usr/local/lib/node_modules/.bin/tool',
    isActive: true,
    manageable: true,
    provenanceKind: 'npm',
    provenanceConfidence: 'confirmed',
  });
  const pathOverride = makeInstall({
    id: 'path',
    realpath: '/custom/tool',
    pathEntry: '/custom/tool',
    isActive: false,
    manageable: false,
    status: 'missing',
  });

  const installs = [npmInstall, pathOverride];

  it('finds by auto ref (isActive installation)', () => {
    expect(findInstallation(installs, { kind: 'auto' })?.isActive).toBe(true);
  });

  it('finds by method ref (manageable + provenance match)', () => {
    expect(findInstallation(installs, { kind: 'method', method: 'npm' })?.provenance.kind).toBe(
      'npm'
    );
  });

  it('finds by pinned ref (realpath match)', () => {
    const ref: SelectedSource = {
      kind: 'pinned',
      realpath: '/usr/local/lib/node_modules/.bin/tool',
    };
    expect(findInstallation(installs, ref)?.realpath).toBe('/usr/local/lib/node_modules/.bin/tool');
  });

  it('finds path override by id', () => {
    expect(findInstallation(installs, { kind: 'path', path: '/custom/tool' })?.id).toBe('path');
  });

  it('returns undefined for missing cli ref', () => {
    expect(findInstallation(installs, { kind: 'cli', command: 'tool' })).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// toSelection
// ---------------------------------------------------------------------------

describe('toSelection', () => {
  it('builds pinned selection', () => {
    expect(toSelection({ kind: 'pinned', realpath: '/opt/homebrew/bin/tool' })).toEqual({
      kind: 'pinned',
      realpath: '/opt/homebrew/bin/tool',
    });
  });

  it('builds path selection', () => {
    expect(toSelection({ kind: 'path', path: '' }, { path: '/usr/bin/foo' })).toEqual({
      kind: 'path',
      path: '/usr/bin/foo',
    });
  });

  it('builds cli selection', () => {
    expect(toSelection({ kind: 'cli', command: '' }, { cli: 'foo' })).toEqual({
      kind: 'cli',
      command: 'foo',
    });
  });

  it('builds method selection', () => {
    expect(toSelection({ kind: 'method', method: 'npm' })).toEqual({
      kind: 'method',
      method: 'npm',
    });
  });

  it('returns null for auto (clear override)', () => {
    expect(toSelection({ kind: 'auto' })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// buildSourceRows
// ---------------------------------------------------------------------------

describe('buildSourceRows', () => {
  it('includes auto as the first row', () => {
    const rows = buildSourceRows(installOptions, []);
    expect(rows[0]?.ref.kind).toBe('auto');
  });

  it('shows install option method rows when no detected installations', () => {
    const rows = buildSourceRows(installOptions, []);
    const methodRows = rows.filter((r) => r.ref.kind === 'method');
    const methods = methodRows.map((r) => r.ref.kind === 'method' && r.ref.method);
    expect(methods).toContain('npm');
    expect(methods).toContain('homebrew');
  });

  it('always appends path and cli override rows', () => {
    const rows = buildSourceRows(installOptions, []);
    const refs = rows.map((r) => r.ref.kind);
    expect(refs).toContain('path');
    expect(refs).toContain('cli');
  });

  it('shows detected installation as pinned row when npm is present', () => {
    const npmInst = makeInstall({
      realpath: '/usr/local/lib/node_modules/mytool/bin/mytool',
      isActive: true,
      manageable: true,
      provenanceKind: 'npm',
      provenanceConfidence: 'confirmed',
    });
    const rows = buildSourceRows(installOptions, [npmInst]);
    const pinnedRows = rows.filter((r) => r.ref.kind === 'pinned');
    expect(pinnedRows).toHaveLength(1);
    expect(pinnedRows[0]?.status).toBe('available');
    // npm is detected → npm install option row should be suppressed
    const methodRows = rows.filter(
      (r) => r.ref.kind === 'method' && r.ref.kind === 'method' && r.ref.method === 'npm'
    );
    expect(methodRows).toHaveLength(0);
    // homebrew still undetected → homebrew method row present
    const homebrewMethod = rows.filter(
      (r) => r.ref.kind === 'method' && r.ref.method === 'homebrew'
    );
    expect(homebrewMethod).toHaveLength(1);
  });

  it('auto row shows missing when no installation is active', () => {
    const rows = buildSourceRows(installOptions, []);
    const autoRow = rows.find((r) => r.ref.kind === 'auto');
    expect(autoRow?.status).toBe('missing');
  });

  it('auto row shows available when an active installation exists', () => {
    const activeInst = makeInstall({ realpath: '/usr/bin/tool', isActive: true });
    const rows = buildSourceRows(installOptions, [activeInst]);
    const autoRow = rows.find((r) => r.ref.kind === 'auto');
    expect(autoRow?.status).toBe('available');
  });

  it('auto row exposes the resolved active path as displayPath', () => {
    const activeInst = makeInstall({
      realpath: '/opt/homebrew/Cellar/tool/1.0.0/bin/tool',
      pathEntry: '/opt/homebrew/bin/tool',
      isActive: true,
    });
    const rows = buildSourceRows(installOptions, [activeInst]);
    const autoRow = rows.find((r) => r.ref.kind === 'auto');
    expect(autoRow?.displayPath).toBe('/opt/homebrew/bin/tool');
  });

  it('auto row has no displayPath when nothing is active', () => {
    const rows = buildSourceRows(installOptions, []);
    const autoRow = rows.find((r) => r.ref.kind === 'auto');
    expect(autoRow?.displayPath).toBeUndefined();
  });

  it('marks npm install option as recommended', () => {
    const rows = buildSourceRows(installOptions, []);
    const npmRow = rows.find((r) => r.ref.kind === 'method' && r.ref.method === 'npm');
    expect(npmRow?.recommended).toBe(true);
  });

  it('multiple detected installations appear as separate pinned rows', () => {
    const inst1 = makeInstall({
      realpath: '/opt/homebrew/Cellar/tool/1.0.0/bin/tool',
      isActive: true,
      provenanceKind: 'homebrew',
      provenanceConfidence: 'confirmed',
    });
    const inst2 = makeInstall({
      realpath: '/usr/local/lib/node_modules/.bin/tool',
      isActive: false,
      provenanceKind: 'npm',
      provenanceConfidence: 'confirmed',
    });
    const rows = buildSourceRows(installOptions, [inst1, inst2]);
    const pinnedRows = rows.filter((r) => r.ref.kind === 'pinned');
    expect(pinnedRows).toHaveLength(2);
    // Both npm and homebrew are detected → no method rows for them
    const methodRows = rows.filter((r) => r.ref.kind === 'method');
    expect(methodRows).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// refFromUsed
// ---------------------------------------------------------------------------

describe('refFromUsed', () => {
  it('returns auto when used is undefined', () => {
    expect(refFromUsed(undefined)).toEqual({ kind: 'auto' });
  });

  it('returns auto for auto SelectedSource', () => {
    expect(refFromUsed({ kind: 'auto' })).toEqual({ kind: 'auto' });
  });

  it('returns pinned ref for pinned SelectedSource', () => {
    const pinned: SelectedSource = { kind: 'pinned', realpath: '/opt/homebrew/bin/tool' };
    expect(refFromUsed(pinned)).toEqual(pinned);
  });

  it('returns method ref for method SelectedSource', () => {
    expect(refFromUsed({ kind: 'method', method: 'npm' })).toEqual({
      kind: 'method',
      method: 'npm',
    });
  });

  it('returns path ref for path SelectedSource', () => {
    const pathSrc: SelectedSource = { kind: 'path', path: '/usr/bin/foo' };
    expect(refFromUsed(pathSrc)).toEqual(pathSrc);
  });

  it('returns cli ref for cli SelectedSource', () => {
    const cliSrc: SelectedSource = { kind: 'cli', command: 'foo' };
    expect(refFromUsed(cliSrc)).toEqual(cliSrc);
  });
});

// ---------------------------------------------------------------------------
// seedSource logic — tests use the same primitives to replicate the helper
// behaviour without importing it directly from the React module.
// ---------------------------------------------------------------------------

/** Replicates InstallSection.seedSource logic for unit-testing purposes. */
function seedSource(
  used: SelectedSource | undefined,
  status: string,
  opts: InstallOption[]
): SelectedSource {
  const liveRef = refFromUsed(used);
  if (liveRef.kind !== 'auto') return liveRef;
  if (status !== 'available') {
    const rec = opts.find((o) => o.recommended);
    if (rec) return { kind: 'method', method: rec.method } as SelectedSource;
  }
  return { kind: 'auto' };
}

describe('seedSource (initial selectedSource seeding)', () => {
  const optsWithRecommended: InstallOption[] = [
    { method: 'homebrew', command: 'brew install mytool', recommended: true },
    { method: 'npm', command: 'npm install -g mytool' },
  ];
  const optsNoRecommended: InstallOption[] = [{ method: 'npm', command: 'npm install -g mytool' }];

  it('returns the persisted selection when used is an explicit method', () => {
    const used: SelectedSource = { kind: 'method', method: 'npm' };
    expect(seedSource(used, 'missing', optsWithRecommended)).toEqual(used);
  });

  it('returns the persisted pinned selection', () => {
    const used: SelectedSource = { kind: 'pinned', realpath: '/opt/homebrew/bin/tool' };
    expect(seedSource(used, 'available', optsWithRecommended)).toEqual(used);
  });

  it('returns the persisted path override regardless of status', () => {
    const used: SelectedSource = { kind: 'path', path: '/custom/tool' };
    expect(seedSource(used, 'available', optsWithRecommended)).toEqual(used);
  });

  it('returns recommended method for uninstalled agents with no prior selection', () => {
    expect(seedSource(undefined, 'missing', optsWithRecommended)).toEqual({
      kind: 'method',
      method: 'homebrew',
    });
  });

  it('returns recommended method when used is auto and agent is not installed', () => {
    expect(seedSource({ kind: 'auto' }, 'missing', optsWithRecommended)).toEqual({
      kind: 'method',
      method: 'homebrew',
    });
  });

  it('returns auto for an installed agent even when a recommended option exists', () => {
    expect(seedSource({ kind: 'auto' }, 'available', optsWithRecommended)).toEqual({
      kind: 'auto',
    });
  });

  it('returns auto when no options have recommended flag', () => {
    expect(seedSource(undefined, 'missing', optsNoRecommended)).toEqual({ kind: 'auto' });
  });

  it('returns auto when installOptions is empty', () => {
    expect(seedSource(undefined, 'missing', [])).toEqual({ kind: 'auto' });
  });
});

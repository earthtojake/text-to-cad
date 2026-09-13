import { describe, expect, it } from 'vitest';
import type { DurableWorkspaceRecord } from './persistence/record-store';
import {
  applyLegacyLifecycleSettingsImport,
  applyPersonalProjectConfigPatch,
  collectProjectConfigSources,
  resolveProjectConfig,
} from './project-config';

function record(
  id: string,
  path: string,
  overrides: Partial<DurableWorkspaceRecord> = {}
): DurableWorkspaceRecord {
  return {
    id,
    kind: 'worktree',
    path,
    parentId: 'repo',
    origin: 'registered',
    gitAdminName: null,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1,
    updatedAt: 1,
    lastObservedAt: 1,
    ...overrides,
  };
}

describe('project lifecycle config resolver', () => {
  it('collects team sources root-first by working directory and ignores duplicate paths', () => {
    const records = [
      record('wt-z', '/project/z'),
      record('duplicate', '/project/a'),
      record('repo', '/project', { kind: 'repository', parentId: null }),
      record('wt-a', '/project/a'),
    ];
    const configs = new Map([
      [
        'repo',
        {
          config: { preservePatterns: ['root/**'], scripts: { setup: 'root setup' } },
          parseError: false,
        },
      ],
      [
        'wt-a',
        {
          config: { preservePatterns: [], scripts: { run: 'a run' }, shellSetup: 'a shell' },
          parseError: false,
        },
      ],
      [
        'duplicate',
        {
          config: { scripts: { run: 'duplicate run' } },
          parseError: false,
        },
      ],
      [
        'wt-z',
        {
          config: { scripts: { teardown: 'z teardown' } },
          parseError: false,
        },
      ],
    ]);

    expect(collectProjectConfigSources(records, configs)).toEqual({
      preservePatterns: [
        {
          workspaceId: 'repo',
          path: '/project/.emdash.json',
          value: ['root/**'],
        },
      ],
      prepare: [],
      setup: [
        {
          workspaceId: 'repo',
          path: '/project/.emdash.json',
          value: 'root setup',
        },
      ],
      run: [
        {
          workspaceId: 'duplicate',
          path: '/project/a/.emdash.json',
          value: 'duplicate run',
        },
      ],
      teardown: [
        {
          workspaceId: 'wt-z',
          path: '/project/z/.emdash.json',
          value: 'z teardown',
        },
      ],
      shellSetup: [],
    });
  });

  it('resolves preserve patterns by replacement with an empty built-in fallback', () => {
    expect(
      resolveProjectConfig({
        personalConfig: { preservePatterns: [] },
        workspaceConfig: { preservePatterns: ['team/**'] },
        hostSettings: {},
      }).resolved.preservePatterns
    ).toEqual({ value: [], from: 'personal' });

    expect(
      resolveProjectConfig({
        personalConfig: {},
        workspaceConfig: { preservePatterns: ['team/**'] },
        hostSettings: {},
      }).resolved.preservePatterns
    ).toEqual({ value: ['team/**'], from: 'team' });

    expect(
      resolveProjectConfig({
        personalConfig: {},
        workspaceConfig: {},
        hostSettings: {},
      }).resolved.preservePatterns
    ).toEqual({ value: [], from: 'built-in' });
  });

  it('resolves each field personal > team > host default > built-in with provenance', () => {
    const resolved = resolveProjectConfig({
      personalConfig: {
        scripts: { setup: 'personal setup' },
        autoRunSetup: false,
      },
      workspaceConfig: {
        scripts: { setup: 'team setup', run: 'team run' },
        shellSetup: 'team shell',
      },
      hostSettings: { shellSetup: 'host shell' },
    });

    expect(resolved).toEqual({
      resolved: {
        preservePatterns: { value: [], from: 'built-in' },
        setup: { value: 'personal setup', from: 'personal' },
        run: { value: 'team run', from: 'team' },
        shellSetup: { value: 'team shell', from: 'team' },
        autoRunSetup: { value: false, from: 'personal' },
        autoRunRun: { value: false, from: 'built-in' },
      },
    });
  });

  it('uses the host shell default when the workspace has no shell setup', () => {
    const resolved = resolveProjectConfig({
      personalConfig: {},
      workspaceConfig: {},
      hostSettings: { shellSetup: 'host shell' },
    });
    expect(resolved.resolved.shellSetup).toEqual({
      value: 'host shell',
      from: 'host-default',
    });
  });

  it('patches personal fields without migration semantics', () => {
    const current = {
      preservePatterns: ['old/**'],
      scripts: { setup: 'personal setup' },
      autoRunRun: true,
    };
    expect(
      applyPersonalProjectConfigPatch(current, {
        workspaceId: 'repo',
        patch: {
          preservePatterns: [],
          scripts: { setup: null, run: 'pnpm dev' },
          autoRunRun: false,
        },
      })
    ).toEqual({ preservePatterns: [], scripts: { run: 'pnpm dev' } });
  });

  it('imports legacy settings only where personal fields are absent', () => {
    const current = {
      preservePatterns: ['personal/**'],
      scripts: { setup: 'personal setup' },
      autoRunRun: true,
    };
    expect(
      applyLegacyLifecycleSettingsImport(current, {
        workspaceId: 'repo',
        settings: {
          preservePatterns: [],
          scripts: { setup: 'legacy setup', teardown: 'legacy teardown' },
          autoRunRun: false,
        },
      })
    ).toEqual({
      preservePatterns: ['personal/**'],
      scripts: { setup: 'personal setup', teardown: 'legacy teardown' },
      autoRunRun: true,
    });

    expect(
      applyLegacyLifecycleSettingsImport(
        {},
        { workspaceId: 'repo', settings: { preservePatterns: [] } }
      )
    ).toEqual({ preservePatterns: [] });
  });
});

import type { ProjectConfigState } from '@emdash/core/runtimes/workspace-registry/api';
import { createManualClock } from '@emdash/shared/testing';
import { createEventStreamHost } from '@emdash/wire/live';
import { cell, expose, flushStateTurn } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { observable } from 'mobx';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { projectConfigDomainsFromState } from '../../project-settings-page';
import { projectsWireContract } from '../../wire-contract';
import type { ProjectHostAccess, ProjectHostAccessState } from './project-context';
import { ProjectSettingsStore } from './project-settings-store';

let configState: ReturnType<typeof cell<ProjectConfigState>>;
let getProjectSettingsPage: ReturnType<typeof vi.fn>;
let wire: ReturnType<typeof createProjectsWire> | undefined;

vi.mock('../client', () => ({
  getProjectsWireClient: async () => wire!.client,
}));

function projectConfig(setup: string): ProjectConfigState {
  return {
    workspaceId: 'repo-1',
    repositoryId: 'repo-1',
    resolved: {
      preservePatterns: { value: [], from: 'built-in' },
      setup: { value: setup, from: 'personal' },
      autoRunSetup: { value: true, from: 'built-in' },
      autoRunRun: { value: false, from: 'built-in' },
    },
    personalConfig: { scripts: { setup } },
    sources: {
      preservePatterns: [],
      prepare: [],
      setup: [],
      run: [],
      teardown: [],
      shellSetup: [],
    },
    legacyDesktopSettingsMigrated: true,
  };
}

function settingsPage(setup: string) {
  const hostDomains = projectConfigDomainsFromState(projectConfig(setup), []);
  return {
    durable: {
      gitIdentity: { stored: {} },
      placement: {
        stored: {},
      },
    },
    host: {
      kind: 'observed' as const,
      observedAt: 1_723_500_000_000,
      value: {
        domains: {
          ...hostDomains,
          placement: {
            layers: {
              hostWorktreeRoot: null,
              builtInWorktreeRoot: '/tmp/worktrees',
              homeDirectory: '/tmp',
            },
            resolved: {
              worktreeRoot: {
                value: '/tmp/worktrees',
                provenance: { kind: 'inferred' as const, from: 'built-in default' },
              },
            },
          },
        },
        configMigrations: [],
        shouldPromptConfigMigration: false,
      },
    },
  };
}

function projectHostAccess(initial: ProjectHostAccessState) {
  const state = observable.box(initial, { deep: false });
  const host: ProjectHostAccess = {
    get state() {
      return state.get();
    },
    get liveAction() {
      const current = state.get();
      return current.kind === 'ready'
        ? { kind: 'enabled' as const }
        : { kind: 'disabled' as const, state: current };
    },
    observe(observation) {
      if (observation.kind === 'never-observed') return { kind: 'unavailable' };
      return state.get().kind === 'ready'
        ? { kind: 'fresh', value: observation.value, observedAt: observation.observedAt }
        : { kind: 'stale', value: observation.value, observedAt: observation.observedAt };
    },
    requireLive: vi.fn(),
    recover: vi.fn(),
  };
  return { host, state };
}

function unavailableSettingsPage() {
  return {
    durable: {
      gitIdentity: {
        stored: {
          baseRemote: 'origin',
          githubAccount: { kind: 'none' as const },
        },
      },
      placement: {
        stored: { tmux: true },
      },
    },
    host: { kind: 'never-observed' as const },
  };
}

beforeEach(() => {
  configState = cell(projectConfig('first setup'));
  getProjectSettingsPage = vi.fn(async () => ({
    success: true as const,
    data: settingsPage('first setup'),
  }));
  wire = createProjectsWire();
});

afterEach(async () => {
  await wire?.dispose();
  wire = undefined;
  vi.clearAllMocks();
});

describe('ProjectSettingsStore offline settings', () => {
  it('loads durable settings without Host access and promotes retained Host settings to stale', async () => {
    const access = projectHostAccess({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });
    getProjectSettingsPage.mockResolvedValueOnce({
      success: true,
      data: unavailableSettingsPage(),
    });
    const store = new ProjectSettingsStore('project-1', access.host);

    await store.load();

    expect(store.durableDomains).toEqual(unavailableSettingsPage().durable);
    expect(store.hostDomains).toEqual({ kind: 'unavailable' });

    getProjectSettingsPage.mockResolvedValueOnce({
      success: true,
      data: settingsPage('recovered setup'),
    });
    access.state.set({ kind: 'ready', hostGeneration: 2 });
    await store.load();
    expect(store.hostDomains).toMatchObject({
      kind: 'fresh',
      value: {
        domains: {
          lifecycle: { personal: { scripts: { setup: 'recovered setup' } } },
        },
      },
    });

    access.state.set({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });
    expect(store.hostDomains).toMatchObject({
      kind: 'stale',
      value: {
        domains: {
          lifecycle: { personal: { scripts: { setup: 'recovered setup' } } },
        },
      },
    });

    getProjectSettingsPage.mockResolvedValueOnce({
      success: true,
      data: unavailableSettingsPage(),
    });
    await store.load();
    expect(store.hostDomains).toMatchObject({ kind: 'stale' });
    store.dispose();
  });
});

describe('ProjectSettingsStore project config live model', () => {
  it('updates renderer domain snapshots from live config without refetching the page', async () => {
    const access = projectHostAccess({ kind: 'ready', hostGeneration: 1 });
    const clock = createManualClock(1_786_000_000_000);
    const store = new ProjectSettingsStore('project-1', access.host, clock);
    await store.load();
    expect(store.domains?.lifecycle.personal.scripts?.setup).toBe('first setup');

    configState.set(projectConfig('second setup'));
    await waitFor(() => store.domains?.lifecycle.personal.scripts?.setup === 'second setup');

    expect(store.domains?.lifecycle.resolved.setup?.value).toBe('second setup');
    expect(store.hostDomains).toMatchObject({ observedAt: 1_786_000_000_000 });
    expect(getProjectSettingsPage).toHaveBeenCalledTimes(1);
    store.dispose();
  });
});

function createProjectsWire() {
  const events = createEventStreamHost(projectsWireContract.events);
  const projectConfigProvider = expose(projectsWireContract.projectConfig, {
    current: () => configState,
  });
  const projectListProvider = expose(projectsWireContract.projectList, {
    list: cell({ projects: [] }),
  });
  const creationProvider = expose(projectsWireContract.creation, {
    state: () => cell({ phase: 'error' as const, message: 'unused' }),
  });
  const directoryTreeProvider = expose(projectsWireContract.directoryTree, {
    tree: () => cell(undefined as never),
  });
  const attachmentsProvider = expose(projectsWireContract.attachments, {
    state: () => cell({ kind: 'absent' as const }),
  });
  const testWire = createTestWire(projectsWireContract, {
    events,
    projectConfig: projectConfigProvider,
    projectList: projectListProvider,
    attachments: attachmentsProvider,
    creation: creationProvider,
    directoryTree: directoryTreeProvider,
    getProjectSettingsPage,
    recoverAttachment: async () => ({ success: true as const, data: undefined }),
    create: {
      run: async () => ({
        success: false as const,
        error: { type: 'unused', message: 'unused' },
      }),
    },
    delete: async () => ({ success: true as const, data: {} }),
  } as never);
  return {
    ...testWire,
    async dispose() {
      await testWire.dispose();
      events.dispose();
    },
  };
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let index = 0; index < 50; index += 1) {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    flushStateTurn();
    if (predicate()) return;
  }
  expect(predicate()).toBe(true);
}

import path from 'node:path';
import type { EmdashConfig, EmdashScriptsConfig } from '#primitives/emdash-config/api';
import type {
  ImportLegacyLifecycleSettingsInput,
  PatchPersonalProjectConfigInput,
  PersonalProjectConfig,
  ProjectConfigSources,
  ResolvedProjectConfig,
} from '../api';
import type { WorkspaceConfigEntry } from './config-model';
import type { DurableWorkspaceRecord } from './persistence/record-store';

export const BUILT_IN_AUTO_RUN_SETUP = true;
export const BUILT_IN_AUTO_RUN_RUN = false;
export const BUILT_IN_PRESERVE_PATTERNS: readonly string[] = [];

export type ProjectConfigHostDefaults = { shellSetup?: string };

export function resolveProjectConfig(input: {
  personalConfig: PersonalProjectConfig;
  workspaceConfig: EmdashConfig;
  hostSettings: ProjectConfigHostDefaults;
}): { resolved: ResolvedProjectConfig } {
  const personalPreservePatterns = input.personalConfig.preservePatterns;
  const teamPreservePatterns = input.workspaceConfig.preservePatterns;
  const resolved = {
    preservePatterns:
      personalPreservePatterns !== undefined
        ? { value: [...personalPreservePatterns], from: 'personal' as const }
        : teamPreservePatterns !== undefined
          ? { value: [...teamPreservePatterns], from: 'team' as const }
          : { value: [...BUILT_IN_PRESERVE_PATTERNS], from: 'built-in' as const },
  } as ResolvedProjectConfig;
  for (const script of ['prepare', 'setup', 'run', 'teardown'] as const) {
    const personal = input.personalConfig.scripts?.[script];
    const team = input.workspaceConfig.scripts?.[script];
    if (personal !== undefined) {
      resolved[script] = { value: personal, from: 'personal' };
    } else if (team !== undefined) {
      resolved[script] = { value: team, from: 'team' };
    }
  }

  const teamShellSetup = input.workspaceConfig.shellSetup;
  const hostShellSetup = input.hostSettings.shellSetup;
  if (teamShellSetup !== undefined) {
    resolved.shellSetup = { value: teamShellSetup, from: 'team' };
  } else if (hostShellSetup !== undefined) {
    resolved.shellSetup = { value: hostShellSetup, from: 'host-default' };
  }
  resolved.autoRunSetup =
    input.personalConfig.autoRunSetup === undefined
      ? { value: BUILT_IN_AUTO_RUN_SETUP, from: 'built-in' }
      : { value: input.personalConfig.autoRunSetup, from: 'personal' };
  resolved.autoRunRun =
    input.personalConfig.autoRunRun === undefined
      ? { value: BUILT_IN_AUTO_RUN_RUN, from: 'built-in' }
      : { value: input.personalConfig.autoRunRun, from: 'personal' };

  return { resolved };
}

/**
 * Aggregates the team config files represented by a project's records. Sources are
 * root-first, then ordered by working-directory path and record id. If corrupt state
 * contains duplicate working-directory records, the root wins; otherwise the lowest
 * record id wins. Each working directory therefore contributes at most once.
 */
export function collectProjectConfigSources(
  records: readonly DurableWorkspaceRecord[],
  configs: Pick<ReadonlyMap<string, WorkspaceConfigEntry>, 'get'>
): ProjectConfigSources {
  const sources = emptyProjectConfigSources();
  const ordered = [...records].sort((left, right) => {
    const leftRoot = left.parentId === null ? 0 : 1;
    const rightRoot = right.parentId === null ? 0 : 1;
    return (
      leftRoot - rightRoot || compareText(left.path, right.path) || compareText(left.id, right.id)
    );
  });
  const seenPaths = new Set<string>();

  for (const record of ordered) {
    if (seenPaths.has(record.path)) continue;
    seenPaths.add(record.path);
    const entry = configs.get(record.id);
    if (!entry) continue;
    const configPath = path.join(record.path, '.hardcore.json');
    if (entry.config.preservePatterns !== undefined) {
      sources.preservePatterns.push({
        workspaceId: record.id,
        path: configPath,
        value: [...entry.config.preservePatterns],
      });
    }
    for (const script of ['prepare', 'setup', 'run', 'teardown'] as const) {
      const value = entry.config.scripts?.[script];
      if (value !== undefined) {
        sources[script].push({ workspaceId: record.id, path: configPath, value });
      }
    }
    if (entry.config.shellSetup !== undefined) {
      sources.shellSetup.push({
        workspaceId: record.id,
        path: configPath,
        value: entry.config.shellSetup,
      });
    }
  }

  return sources;
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function applyPersonalProjectConfigPatch(
  current: PersonalProjectConfig,
  input: PatchPersonalProjectConfigInput
): PersonalProjectConfig {
  const next: PersonalProjectConfig = {
    ...current,
    ...(current.scripts ? { scripts: { ...current.scripts } } : {}),
  };

  for (const script of ['prepare', 'setup', 'run', 'teardown'] as const) {
    const value = input.patch.scripts?.[script];
    if (value === undefined) continue;
    if (value === null) delete next.scripts?.[script];
    else (next.scripts ??= {})[script] = value;
  }

  if (input.patch.preservePatterns !== undefined) {
    if (input.patch.preservePatterns === null) delete next.preservePatterns;
    else next.preservePatterns = [...input.patch.preservePatterns];
  }

  applyToggle(next, 'autoRunSetup', input.patch.autoRunSetup, BUILT_IN_AUTO_RUN_SETUP);
  applyToggle(next, 'autoRunRun', input.patch.autoRunRun, BUILT_IN_AUTO_RUN_RUN);

  if (next.scripts && Object.keys(next.scripts).length === 0) delete next.scripts;
  return next;
}

export function applyLegacyLifecycleSettingsImport(
  current: PersonalProjectConfig,
  input: ImportLegacyLifecycleSettingsInput
): PersonalProjectConfig {
  const scripts: EmdashScriptsConfig = { ...current.scripts };
  for (const script of ['prepare', 'setup', 'run', 'teardown'] as const) {
    if (scripts[script] === undefined && input.settings.scripts?.[script] !== undefined) {
      scripts[script] = input.settings.scripts[script];
    }
  }
  const next: PersonalProjectConfig = {
    ...current,
    ...(Object.keys(scripts).length > 0 ? { scripts } : {}),
  };
  if (next.preservePatterns === undefined && input.settings.preservePatterns !== undefined) {
    next.preservePatterns = [...input.settings.preservePatterns];
  }
  if (next.autoRunSetup === undefined && input.settings.autoRunSetup !== undefined) {
    applyToggle(next, 'autoRunSetup', input.settings.autoRunSetup, BUILT_IN_AUTO_RUN_SETUP);
  }
  if (next.autoRunRun === undefined && input.settings.autoRunRun !== undefined) {
    applyToggle(next, 'autoRunRun', input.settings.autoRunRun, BUILT_IN_AUTO_RUN_RUN);
  }
  return next;
}

function applyToggle(
  next: PersonalProjectConfig,
  key: 'autoRunSetup' | 'autoRunRun',
  value: boolean | null | undefined,
  builtIn: boolean
): void {
  if (value === undefined) return;
  if (value === null || value === builtIn) delete next[key];
  else next[key] = value;
}

export function emptyProjectConfigSources(): ProjectConfigSources {
  return { preservePatterns: [], prepare: [], setup: [], run: [], teardown: [], shellSetup: [] };
}

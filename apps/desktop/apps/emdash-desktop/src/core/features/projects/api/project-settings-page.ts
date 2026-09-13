import type {
  PatchPersonalProjectConfigInput,
  PersonalProjectConfig,
  ProjectConfigState,
  ResolvedProjectConfig,
} from '@emdash/core/runtimes/workspace-registry/api';
import type {
  AgentGitCredentialsSetting,
  PlacementContext,
  ProjectConfigMigration,
  ProjectSettingsWriteTargetOption,
  Resolved,
  StoredDefaultBranch,
  StoredGithubAccount,
  StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import type { ProjectAttachmentError } from './attachments';
import type { HostObservation } from './host-observation';

type LifecycleScript = 'prepare' | 'setup' | 'run' | 'teardown';

export type ProjectSettingsDomainSource<T> = {
  workspaceId: string;
  label: string;
  /** Working directory containing the source `.emdash.json`. */
  path: string;
  configPath: string;
  value: T;
};

export type ProjectLifecycleDomainSnapshot = {
  personal: Pick<PersonalProjectConfig, 'scripts' | 'autoRunSetup' | 'autoRunRun'>;
  /** Raw values from the repository's own `.emdash.json`. */
  team: { scripts?: Partial<Record<LifecycleScript, string>> };
  resolved: Pick<
    ResolvedProjectConfig,
    LifecycleScript | 'autoRunSetup' | 'autoRunRun' | 'shellSetup'
  >;
  /** Aggregated `.emdash.json` values across active working directories. */
  sources: {
    [K in LifecycleScript]: ProjectSettingsDomainSource<string>[];
  };
  writeTargets: ProjectSettingsWriteTargetOption[];
};

export type ProjectFileHandlingDomainSnapshot = {
  personal: Pick<PersonalProjectConfig, 'preservePatterns'>;
  /** Raw value from the repository's own `.emdash.json`. */
  team: Pick<PersonalProjectConfig, 'preservePatterns'>;
  resolved: Pick<ResolvedProjectConfig, 'preservePatterns'>;
  /** Aggregated `.emdash.json` values across active working directories. */
  sources: ProjectSettingsDomainSource<string[]>[];
  writeTargets: ProjectSettingsWriteTargetOption[];
};

export type ProjectGitIdentityDomainSnapshot = {
  stored: Pick<
    StoredProjectGitSettings,
    'defaultBranch' | 'baseRemote' | 'pushRemote' | 'githubAccount' | 'agentGitCredentials'
  >;
};

export type ProjectPlacementDomainSnapshot = {
  stored: {
    worktreeRoot?: string;
    tmux?: boolean;
  };
  layers: PlacementContext;
  resolved: {
    worktreeRoot: Resolved<string>;
    tmux: Resolved<boolean>;
  };
};

export type ProjectSettingsDomains = {
  lifecycle: ProjectLifecycleDomainSnapshot;
  fileHandling: ProjectFileHandlingDomainSnapshot;
  gitIdentity: ProjectGitIdentityDomainSnapshot;
  placement: ProjectPlacementDomainSnapshot;
};

export type ProjectDurableSettingsDomains = {
  gitIdentity: ProjectGitIdentityDomainSnapshot;
  placement: Pick<ProjectPlacementDomainSnapshot, 'stored'>;
};

export type ProjectHostSettingsDomains = {
  lifecycle: ProjectLifecycleDomainSnapshot;
  fileHandling: ProjectFileHandlingDomainSnapshot;
  placement: Omit<ProjectPlacementDomainSnapshot, 'stored'>;
};

type PersonalProjectConfigPatch = PatchPersonalProjectConfigInput['patch'];

export type ProjectGitIdentityStoredPatch = {
  defaultBranch?: StoredDefaultBranch | null;
  baseRemote?: string | null;
  pushRemote?: string | null;
  githubAccount?: StoredGithubAccount | null;
  agentGitCredentials?: AgentGitCredentialsSetting | null;
};

export type ProjectPlacementStoredPatch = {
  worktreeRoot?: string | null;
  tmux?: boolean | null;
};

export type ProjectSettingsDomainPatch = {
  lifecycle?: {
    personal: Pick<PersonalProjectConfigPatch, 'scripts' | 'autoRunSetup' | 'autoRunRun'>;
  };
  fileHandling?: {
    personal: Pick<PersonalProjectConfigPatch, 'preservePatterns'>;
  };
  gitIdentity?: {
    stored: ProjectGitIdentityStoredPatch;
  };
  placement?: {
    stored: ProjectPlacementStoredPatch;
  };
};

export type ProjectHostSettingsSnapshot = {
  domains: ProjectHostSettingsDomains;
  configMigrations: ProjectConfigMigration[];
  shouldPromptConfigMigration: boolean;
};

export type ProjectSettingsPage = {
  durable: ProjectDurableSettingsDomains;
  host: HostObservation<ProjectHostSettingsSnapshot>;
};

export type ProjectSettingsError = UpdateProjectSettingsError | ProjectAttachmentError;

export type MigrateProjectConfigResult = {
  page: ProjectSettingsPage;
  migration: ProjectConfigMigration;
};

export function projectConfigDomainsFromState(
  config: ProjectConfigState,
  writeTargets: ProjectSettingsWriteTargetOption[]
): Pick<ProjectSettingsDomains, 'lifecycle' | 'fileHandling'> {
  const source = <T>(entry: {
    workspaceId: string;
    path: string;
    value: T;
  }): ProjectSettingsDomainSource<T> => {
    const target =
      writeTargets.find((candidate) => candidate.configPath === entry.path) ??
      writeTargets.find((candidate) =>
        entry.workspaceId === config.repositoryId
          ? candidate.type === 'project'
          : candidate.sourceWorkspaceId === entry.workspaceId
      );
    return {
      workspaceId: entry.workspaceId,
      label: target?.label ?? 'Workspace',
      path: target?.path ?? entry.path,
      configPath: entry.path,
      value: entry.value,
    };
  };
  const repositorySource = <T>(entries: { workspaceId: string; value: T }[]): T | undefined =>
    entries.find((entry) => entry.workspaceId === config.repositoryId)?.value;
  const teamScripts: Partial<Record<LifecycleScript, string>> = {};
  for (const script of ['prepare', 'setup', 'run', 'teardown'] as const) {
    const value = repositorySource(config.sources[script]);
    if (value !== undefined) teamScripts[script] = value;
  }
  const { preservePatterns: _personalPreservePatterns, ...lifecyclePersonal } =
    config.personalConfig;
  const { preservePatterns: _resolvedPreservePatterns, ...lifecycleResolved } = config.resolved;
  return {
    lifecycle: {
      personal: lifecyclePersonal,
      team: {
        ...(Object.keys(teamScripts).length > 0 ? { scripts: teamScripts } : {}),
      },
      resolved: lifecycleResolved,
      sources: {
        prepare: config.sources.prepare.map(source),
        setup: config.sources.setup.map(source),
        run: config.sources.run.map(source),
        teardown: config.sources.teardown.map(source),
      },
      writeTargets,
    },
    fileHandling: {
      personal: {
        ...(config.personalConfig.preservePatterns !== undefined
          ? { preservePatterns: [...config.personalConfig.preservePatterns] }
          : {}),
      },
      team: {
        ...(repositorySource(config.sources.preservePatterns) !== undefined
          ? {
              preservePatterns: [...repositorySource(config.sources.preservePatterns)!],
            }
          : {}),
      },
      resolved: { preservePatterns: config.resolved.preservePatterns },
      sources: config.sources.preservePatterns.map(source),
      writeTargets,
    },
  };
}

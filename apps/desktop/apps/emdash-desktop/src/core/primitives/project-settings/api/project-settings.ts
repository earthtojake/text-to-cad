import type { EmdashConfig } from '@emdash/core/primitives/emdash-config/api';
import type { Result } from '@emdash/shared';
import z from 'zod';

export const defaultBranchSettingSchema = z.union([
  z.string(),
  z.object({ name: z.string(), remote: z.literal(true) }),
]);

export type DefaultBranchSetting = z.infer<typeof defaultBranchSettingSchema>;

export type ShareableProjectSettings = EmdashConfig;

/**
 * Per-project git credential behavior for agent/terminal PTY sessions
 * (spec: github-git-settings §4). Absence means the default,
 * `effective-account`; emdash's own git operations are unaffected by this
 * setting and always authenticate as the effective account.
 */
export const agentGitCredentialsSettingSchema = z.enum(['effective-account', 'system', 'none']);

export type AgentGitCredentialsSetting = z.infer<typeof agentGitCredentialsSettingSchema>;

export const DEFAULT_AGENT_GIT_CREDENTIALS: AgentGitCredentialsSetting = 'effective-account';

export const baseProjectSettingsSchema = z.object({
  worktreeDirectory: z.string().trim().optional(),
  defaultBranch: defaultBranchSettingSchema.optional(),
  baseRemote: z.string().optional(),
  pushRemote: z.string().optional(),
  githubAccountId: z.string().trim().min(1).nullable().optional(),
  agentGitCredentials: agentGitCredentialsSettingSchema.optional(),
  tmux: z.boolean().optional(),
  autoRunSetupScriptOnTaskCreation: z.boolean().optional(),
  autoRunRunScriptOnTaskCreation: z.boolean().optional(),
});

export type BaseProjectSettings = z.infer<typeof baseProjectSettingsSchema>;

// --- Stored model (spec: github-git-settings §10) -------------------------
// The persisted per-project base settings after lazy migration. Apart from
// named migration markers, only explicit user choices are stored; absence of
// a setting always means "infer". Resolver-facing types live in
// ./effective-settings.

export const storedDefaultBranchSchema = z.object({
  /** Remote the branch lives on; `null` means a local branch. */
  remote: z.string().nullable(),
  branch: z.string(),
});

export const storedGithubAccountSchema = z.union([
  z.object({ kind: z.literal('account'), accountId: z.string().trim().min(1) }),
  z.object({ kind: z.literal('none') }),
]);

export const storedBaseProjectSettingsSchema = z.object({
  /** Renamed from the legacy `worktreeDirectory` key. */
  worktreeRoot: z.string().trim().optional(),
  defaultBranch: storedDefaultBranchSchema.optional(),
  baseRemote: z.string().optional(),
  pushRemote: z.string().optional(),
  githubAccount: storedGithubAccountSchema.optional(),
  agentGitCredentials: agentGitCredentialsSettingSchema.optional(),
  tmux: z.boolean().optional(),
  /** Lazy-migration marker; not a user setting. */
  tmuxDefaultMigrated: z.literal(true).optional(),
});

export type StoredBaseProjectSettings = z.infer<typeof storedBaseProjectSettingsSchema>;

export type ProjectSettingsLoadError =
  | { type: 'not_found'; entity: 'workspace'; workspaceId: string }
  | { type: 'fs_error'; message: string };

export type WorkspaceLifecycleSettings = Pick<EmdashConfig, 'scripts' | 'shellSetup'>;

export type ProjectSettingsLoadResult = Result<
  WorkspaceLifecycleSettings,
  ProjectSettingsLoadError
>;

export type ProjectSettingsWriteTarget =
  | { type: 'project' }
  | { type: 'task'; taskId: string }
  | { type: 'workspace'; workspaceId: string };

export type ProjectSettingsWriteTargetOption = ProjectSettingsWriteTarget & {
  label: string;
  path: string;
  configPath: string;
  /** Registry workspace represented by this working-directory target, when known. */
  sourceWorkspaceId?: string;
};

// shellSetup is deliberately absent: the per-project DB field was retired in favor
// of per-host defaults (host-settings runtime) overridden by workspace .hardcore.json.
export type ShareableProjectSettingsWriteField =
  | 'preservePatterns'
  | 'scripts.prepare'
  | 'scripts.setup'
  | 'scripts.run'
  | 'scripts.teardown';

export const SHAREABLE_PROJECT_SETTINGS_WRITE_FIELDS = [
  'preservePatterns',
  'scripts.prepare',
  'scripts.setup',
  'scripts.run',
  'scripts.teardown',
] as const satisfies ShareableProjectSettingsWriteField[];

export type WriteProjectConfigRequest = {
  target: ProjectSettingsWriteTarget;
  fields: ShareableProjectSettingsWriteField[];
};

export type ProjectConfigMigrationProvider = 'conductor' | 'superset' | 'paseo' | 'codex';

export type ProjectConfigMigration = {
  provider: ProjectConfigMigrationProvider;
  label: string;
  files: string[];
  fields: ShareableProjectSettingsWriteField[];
  unsupportedFields: string[];
};

export type ProjectConfigMigrationDestination = 'local' | 'shared';

export type MigrateProjectConfigRequest = {
  provider: ProjectConfigMigrationProvider;
  destination: ProjectConfigMigrationDestination;
};

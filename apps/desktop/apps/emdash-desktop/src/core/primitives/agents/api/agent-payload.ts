import type { HostDependencyError } from '@emdash/core/primitives/host-dependencies/api';
import type { PluginIconAsset } from '@emdash/shared/plugins';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';

// ---------------------------------------------------------------------------
// Install methods — mirrors INSTALL_METHODS in @emdash/core/services/host-dependencies/api/capability.ts
// ---------------------------------------------------------------------------

export type InstallMethod =
  | 'installer-macos'
  | 'installer-windows'
  | 'installer-linux'
  | 'homebrew'
  | 'winget'
  | 'powershell'
  | 'npm'
  | 'apt'
  | 'curl'
  | 'pip'
  | 'cargo'
  | 'other';

export type InstallOption = {
  method: InstallMethod;
  command: string;
  label?: string;
  recommended?: boolean;
  updateCommand?: string;
  uninstallCommand?: string;
};

// ---------------------------------------------------------------------------
// Installation state — mirrors @emdash/core/services/host-dependencies/node types.ts
// ---------------------------------------------------------------------------

export type DependencyStatus = 'available' | 'missing' | 'error';

/**
 * Installation provenance — mirrors Provenance in @emdash/core/services/host-dependencies/node types.ts.
 */
export type Provenance = {
  kind: InstallMethod | 'manual' | 'version-manager' | 'unknown';
  confidence: 'confirmed' | 'inferred';
  managerRef?: string;
};

/**
 * Persisted discriminated union for a user-chosen install override.
 * null = auto. Never store { kind: 'auto' }.
 * pinned: a specific binary selected by absolute realpath.
 */
export type InstallOverride =
  | { kind: 'pinned'; realpath: string }
  | { kind: 'method'; method: InstallMethod }
  | { kind: 'path'; path: string }
  | { kind: 'cli'; command: string };

/**
 * Runtime / UI union that adds 'auto' to the persisted override kinds.
 */
export type SelectedSource = { kind: 'auto' } | InstallOverride;

/**
 * Returns a stable string key for a SelectedSource.
 * 'auto' | '<realpath>' (pinned) | 'method:<m>' | 'path' | 'cli'
 */
export function sourceKey(s: SelectedSource): string {
  if (s.kind === 'pinned') return s.realpath;
  if (s.kind === 'method') return `method:${s.method}`;
  return s.kind;
}

export type Installation = {
  /**
   * Stable lookup key.
   * Enumerated installs: absolute realpath. Path override: 'path'. CLI override: 'cli'.
   */
  id: string;
  /** Absolute canonical realpath of the binary. */
  realpath: string;
  /** PATH-visible path entry (symlink/shim). Null for off-PATH installs. */
  pathEntry: string | null;
  /** True when this is the current PATH winner (first `which` result). */
  isActive: boolean;
  /** Whether emdash can manage (update/uninstall) this installation. */
  manageable: boolean;
  /** How this binary was installed and how confidently we know it. */
  provenance: Provenance;
  status: DependencyStatus;
  version: string | null;
  latestVersion: string | null;
  updateAvailable: boolean;
};

/**
 * Resolves the active Installation from a list given a SelectedSource.
 * Mirrors resolveActiveInstallation from @emdash/core/services/host-dependencies/node.
 */
export function resolveActiveInstallation(
  installations: Installation[],
  used: SelectedSource
): Installation | undefined {
  if (used.kind === 'auto') return installations.find((i) => i.isActive);
  if (used.kind === 'pinned') return installations.find((i) => i.realpath === used.realpath);
  if (used.kind === 'method') {
    return installations.find((i) => i.provenance.kind === used.method && i.manageable);
  }
  if (used.kind === 'path') return installations.find((i) => i.id === 'path');
  if (used.kind === 'cli') return installations.find((i) => i.id === 'cli');
  return undefined;
}

/** Persisted user preference for which installation to use on a specific host. */
export type HostDependencySelection = InstallOverride | null;

// ---------------------------------------------------------------------------
// Host dependency operation errors
// ---------------------------------------------------------------------------

export type AgentInstallError = HostDependencyError;

export type AgentUpdateError =
  | Exclude<
      HostDependencyError,
      | { type: 'missing' }
      | { type: 'no-install-command' }
      | { type: 'no-update-command' }
      | { type: 'not-detected-after-install' }
    >
  | { type: 'no-update-strategy'; id: string }
  | { type: 'not-detected-after-update'; id: string };

export type AgentUninstallError =
  | Extract<
      HostDependencyError,
      { type: 'unknown-dependency' | 'permission-denied' | 'command-failed' }
    >
  | { type: 'no-uninstall-strategy'; id: string }
  | { type: 'no-uninstall-command'; id: string };

// ---------------------------------------------------------------------------
// Narrowed capability types — only the subset the renderer reads
// ---------------------------------------------------------------------------

export type AgentUpdateStrategy =
  | { kind: 'package-manager' }
  | { kind: 'cli'; args: string[] }
  | { kind: 'auto' }
  | { kind: 'none' };

export type AgentUninstallStrategy =
  | { kind: 'package-manager' }
  | { kind: 'cli'; args: string[] }
  | { kind: 'none' };

export type AgentHostDependencyInfo = {
  updates: { kind: 'supported'; update: AgentUpdateStrategy } | { kind: 'none' };
  uninstall?: AgentUninstallStrategy;
};

export type AgentModelOption = {
  name: string;
  description?: string;
  modelFeatures?: {
    contextWindowSize?: number;
    speed?: number;
    intelligence?: number;
  };
};

export type AgentModelsCapability =
  | { kind: 'none' }
  | { kind: 'selectable'; modelOptions: Record<string, AgentModelOption> };

export type AgentAuthMethod =
  | {
      kind: 'cli-login';
      id: string;
      name: string;
      args: string[];
      description?: string;
    }
  | {
      kind: 'api-key';
      id: string;
      name: string;
      envVars: Array<{ name: string; label: string }>;
      helpUrl?: string;
    };

export type AgentAuthDescriptor =
  | { kind: 'none' }
  | { kind: 'supported'; methods: AgentAuthMethod[] };

export type AgentCapabilities = {
  acp: { kind: string };
  auth: AgentAuthDescriptor;
  hostDependency: AgentHostDependencyInfo;
  models: AgentModelsCapability;
  effort: { kind: string };
  prompt: { kind: string };
  sessions: { kind: string };
  autoApprove: { kind: string };
  hooks: { kind: string; scope?: string };
  mcp: { kind: string };
  plugins: { kind: string };
  trust: { kind: string };
};

export function agentSupportsAcp(capabilities: AgentCapabilities | undefined | null): boolean {
  return capabilities?.acp.kind === 'supported';
}

export function agentSupportsInitialPromptDelivery(
  capabilities: AgentCapabilities | undefined | null
): boolean {
  const kind = capabilities?.prompt?.kind;
  return kind === undefined || kind === 'argv' || kind === 'stdin-pipe';
}

export function agentSupportsAutoApprove(
  capabilities: AgentCapabilities | undefined | null
): boolean {
  return capabilities?.autoApprove.kind === 'supported';
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export type AgentSettings = {
  value: ProviderCustomConfig;
  defaults: ProviderCustomConfig;
  overrides: Partial<ProviderCustomConfig>;
};

// ---------------------------------------------------------------------------
// Top-level DTOs sent over IPC
// ---------------------------------------------------------------------------

/** Static agent metadata; host-independent and returned by `agents.list()`/`agents.get()`. */
export type AgentMetadata = {
  id: string;
  name: string;
  description: string;
  websiteUrl: string;
  icon: PluginIconAsset;
  capabilities: AgentCapabilities;
  /** Link to installation documentation, null if not set by the plugin. */
  installDocs: string | null;
};

/** Host-scoped installation status; returned by `agents.listAgentInstallationStatus()`. */
export type AgentInstallationStatus = {
  id: string;
  connectionId?: string;
  status: DependencyStatus;
  version: string | null;
  latestVersion: string | null;
  updateAvailable: boolean;
  command: string | null;
  installations: Installation[];
  /** The authoritative source (persisted override or auto). */
  used: SelectedSource;
  /** @deprecated Use `used` instead. Kept for backward compat during migration. */
  usedId: string;
  /** Platform-resolved install options for this agent on the host. */
  installOptions: InstallOption[];
};

/** Combined payload — used for gradual renderer migration. */
export type AgentPayload = AgentMetadata &
  Omit<AgentInstallationStatus, 'id'> & {
    settings: AgentSettings;
  };

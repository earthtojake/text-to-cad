import type { TerminalShellId } from '@emdash/core/primitives/terminal-shell/api';
import type { BrowserProfile, BrowserProfileSelection } from '@core/primitives/browser/api';
import type { OpenInAppId } from '@core/primitives/open-in-apps/api/open-in-apps';

export type LocalProjectSettings = {
  defaultProjectsDirectory: string;
  defaultWorktreeDirectory: string;
};

export type ProjectSettings = {
  pushOnCreate: boolean;
  branchPrefix: string;
  appendRandomBranchSuffix: boolean;
  tmuxByDefault: boolean;
};

export type NotificationSettings = {
  enabled: boolean;
  sound: boolean;
  customSoundPath: string;
  osNotifications: boolean;
  soundFocusMode: 'always' | 'unfocused';
};

export type TaskSettings = {
  autoGenerateName: boolean;
  autoApproveByDefault: boolean;
  autoTrustWorktrees: boolean;
  createBranchAndWorktree: boolean;
  deleteBranchByDefault: boolean;
  preserveNameCapitalization: boolean;
  includeIssueContextByDefault: boolean;
};

export type FilesSettings = {
  treeExclude: string[];
  searchExclude: string[];
  watcherExclude: string[];
};

export type TerminalSettings = {
  fontFamily?: string;
  fontSize?: number;
  autoCopyOnSelection: boolean;
  macOptionIsMeta: boolean;
  defaultShell: TerminalShellId;
};

export type Theme = 'emlight' | 'emdark' | null;

export type InterfaceSettings = {
  taskHoverAction: 'delete' | 'archive';
  autoRightSidebarBehavior: boolean;
  showLeftSidebarLineChanges: boolean;
  showLeftSidebarPrStatus: boolean;
  showLeftSidebarTimestamps: boolean;
  hideContextBar: boolean;
};

export type ProviderCustomConfig = {
  extraArgs?: string;
  env?: Record<string, string>;
};
export type ProviderCustomConfigs = Record<string, ProviderCustomConfig>;

export type ChangesViewMode = {
  unstaged: 'flat' | 'tree';
  staged: 'flat' | 'tree';
  pr: 'flat' | 'tree';
};

export type BrowserSettings = {
  defaultProfileId: BrowserProfileSelection;
  relaxCorsForLocalhost: boolean;
  profiles: BrowserProfile[];
};

export type KeyboardSettings = Record<string, string | null | undefined>;

export type OpenInSettings = {
  default: OpenInAppId;
  hidden: OpenInAppId[];
};

export type ChangesSection = keyof ChangesViewMode;
export type ChangesListViewMode = ChangesViewMode[ChangesSection];

export type HostSettings = {
  installBaseUrl: string;
};

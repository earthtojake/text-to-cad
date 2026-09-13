import type { ReactNode } from 'react';

export type CreateTaskNonEmpty<T> = readonly [T, ...T[]];

export type CreateTaskAvailability =
  | { kind: 'available' }
  | { kind: 'unavailable'; reason: string };

export type CreateTaskValidation = { kind: 'valid' } | { kind: 'invalid'; message: string };

export type CreateTaskOptionAvailability = CreateTaskAvailability;

export type CreateTaskSelection<T> = { kind: 'none' } | { kind: 'selected'; option: T };

export type CreateTaskOptionsState<T> =
  | { kind: 'loading' }
  | { kind: 'ready'; items: CreateTaskNonEmpty<T> }
  | { kind: 'refreshing'; items: CreateTaskNonEmpty<T> }
  | {
      kind: 'stale-error';
      items: CreateTaskNonEmpty<T>;
      message: string;
      retryable: boolean;
    }
  | { kind: 'empty' }
  | { kind: 'error'; message: string; retryable: boolean }
  | { kind: 'unavailable'; reason: string };

export interface CreateTaskSearchChoice<T> {
  availability: CreateTaskAvailability;
  query: string;
  selection: CreateTaskSelection<T>;
  options: CreateTaskOptionsState<T>;
}

export interface CreateTaskChoice<T> {
  availability: CreateTaskAvailability;
  selection: CreateTaskSelection<T>;
  options: CreateTaskOptionsState<T>;
}

export interface CreateTaskLiveMessage {
  id: string;
  text: string;
}

export interface CreateTaskAnnouncements {
  polite: CreateTaskLiveMessage | null;
  assertive: CreateTaskLiveMessage | null;
}

export type CreateTaskOverlay =
  | { kind: 'none' }
  | { kind: 'project' }
  | {
      kind: 'create-from';
      nested: 'none' | 'issue-provider' | 'pull-request-status';
    }
  | {
      kind: 'workspace-settings';
      nested: 'none' | 'source-branch' | 'existing-workspace';
    }
  | { kind: 'saved-prompts' }
  | { kind: 'agent' }
  | { kind: 'model' }
  | { kind: 'effort' };

export interface CreateTaskProjectOption {
  id: string;
  label: string;
  path: string;
  location: { kind: 'local' } | { kind: 'ssh'; hostLabel: string };
  artwork?: ReactNode;
  availability: CreateTaskOptionAvailability;
}

export interface CreateTaskProjectState {
  query: string;
  selection: CreateTaskSelection<CreateTaskProjectOption>;
  options: CreateTaskOptionsState<CreateTaskProjectOption>;
}

export type CreateTaskOriginKind = 'branch' | 'issue' | 'pull-request';

export interface CreateTaskBranchOption {
  id: string;
  label: string;
  description: string | null;
  isDefault: boolean;
  availability: CreateTaskOptionAvailability;
}

export interface CreateTaskIssueProviderOption {
  id: string;
  label: string;
  artwork?: ReactNode;
  availability: CreateTaskOptionAvailability;
}

export interface CreateTaskIssueOption {
  id: string;
  providerId: string;
  identifier: string;
  title: string;
  stateLabel: string | null;
  artwork?: ReactNode;
  availability: CreateTaskOptionAvailability;
}

export interface CreateTaskPullRequestOption {
  id: string;
  number: string;
  title: string;
  headBranch: string;
  status: 'open' | 'closed';
  artwork?: ReactNode;
  availability: CreateTaskOptionAvailability;
}

export type CreateTaskOrigin =
  | { kind: 'branch'; option: CreateTaskBranchOption }
  | { kind: 'issue'; option: CreateTaskIssueOption }
  | { kind: 'pull-request'; option: CreateTaskPullRequestOption };

export type CreateTaskOriginSelection =
  | { kind: 'unlinked' }
  | {
      kind: 'linked';
      origin: CreateTaskOrigin;
      validation: CreateTaskValidation;
    };

export type CreateTaskBranchOriginState =
  | { kind: 'unsupported'; reason: string }
  | {
      kind: 'available';
      query: string;
      options: CreateTaskOptionsState<CreateTaskBranchOption>;
    };

export type CreateTaskIssueOriginState =
  | { kind: 'unsupported'; reason: string }
  | {
      kind: 'available';
      query: string;
      provider: CreateTaskChoice<CreateTaskIssueProviderOption>;
      options: CreateTaskOptionsState<CreateTaskIssueOption>;
    };

export type CreateTaskPullRequestOriginState =
  | { kind: 'unsupported'; reason: string }
  | {
      kind: 'available';
      query: string;
      status: 'open' | 'closed';
      options: CreateTaskOptionsState<CreateTaskPullRequestOption>;
    };

export interface CreateTaskOriginState {
  activeKind: CreateTaskOriginKind;
  selection: CreateTaskOriginSelection;
  branch: CreateTaskBranchOriginState;
  issue: CreateTaskIssueOriginState;
  pullRequest: CreateTaskPullRequestOriginState;
}

export type CreateTaskWorkspacePreset =
  | 'new-worktree'
  | 'repo-root'
  | 'use-existing'
  | 'checkout-pr'
  | 'pr-new-branch';

export type CreateTaskWorkspacePresetAvailability = Readonly<
  Record<CreateTaskWorkspacePreset, CreateTaskAvailability>
>;

export interface CreateTaskBranchNameState {
  value: string;
  generatedValue: string;
  source: 'derived' | 'override';
  validation: CreateTaskValidation;
}

export type CreateTaskBooleanControl =
  | { kind: 'supported'; value: boolean }
  | { kind: 'unsupported'; value: false; reason: string };

export interface CreateTaskSetupStep {
  id: string;
  label: string;
  description: string | null;
}

export interface CreateTaskSetupPreview {
  expanded: boolean;
  steps: readonly CreateTaskSetupStep[];
}

export interface CreateTaskExistingWorkspaceOption {
  id: string;
  label: string;
  branch: string | null;
  path: string;
  taskName: string | null;
  changedFiles: number | null;
  linesAdded: number | null;
  linesDeleted: number | null;
  availability: CreateTaskOptionAvailability;
}

export type CreateTaskBranchConflict =
  | { kind: 'none' }
  | {
      kind: 'branch-in-use';
      message: string;
      workspace: CreateTaskExistingWorkspaceOption;
    };

export interface CreateTaskLinkedPullRequestSummary {
  id: string;
  number: string;
  title: string;
  headBranch: string;
}

export type CreateTaskReadyWorkspaceDetail =
  | {
      preset: 'new-worktree';
      mode: 'checkout';
      sourceBranch: CreateTaskSearchChoice<CreateTaskBranchOption>;
      conflict: CreateTaskBranchConflict;
      setup: CreateTaskSetupPreview;
    }
  | {
      preset: 'new-worktree';
      mode: 'create';
      sourceBranch: CreateTaskSearchChoice<CreateTaskBranchOption>;
      branchName: CreateTaskBranchNameState;
      pushBranch: CreateTaskBooleanControl;
      setup: CreateTaskSetupPreview;
    }
  | {
      preset: 'repo-root';
      repositoryPath: string;
      consequence: string;
    }
  | {
      preset: 'use-existing';
      workspace: CreateTaskSearchChoice<CreateTaskExistingWorkspaceOption>;
    }
  | {
      preset: 'checkout-pr';
      pullRequest: CreateTaskLinkedPullRequestSummary;
      setup: CreateTaskSetupPreview;
    }
  | {
      preset: 'pr-new-branch';
      pullRequest: CreateTaskLinkedPullRequestSummary;
      branchName: CreateTaskBranchNameState;
      pushBranch: CreateTaskBooleanControl;
      setup: CreateTaskSetupPreview;
    };

export type CreateTaskWorkspaceDetailState =
  | { kind: 'resolving'; preset: CreateTaskWorkspacePreset }
  | { kind: 'ready'; detail: CreateTaskReadyWorkspaceDetail }
  | {
      kind: 'error';
      preset: CreateTaskWorkspacePreset;
      message: string;
      retryable: boolean;
    }
  | {
      kind: 'unavailable';
      preset: CreateTaskWorkspacePreset;
      reason: string;
      recoverable: boolean;
    };

export type CreateTaskWorkspaceResolution =
  | { kind: 'resolving' }
  | { kind: 'ready-valid' }
  | { kind: 'ready-warning'; message: string }
  | { kind: 'invalid'; message: string }
  | { kind: 'recoverably-unavailable'; reason: string };

export type CreateTaskWorkspaceDestination =
  | { kind: 'resolving' }
  | { kind: 'ready'; path: string; description: string | null }
  | {
      kind: 'fallback';
      path: string;
      configuredPath: string;
      warning: string;
    }
  | { kind: 'unavailable'; reason: string };

export type CreateTaskWorkspaceState =
  | { kind: 'terminally-unavailable'; reason: string }
  | {
      kind: 'inspectable';
      selectedPreset: CreateTaskWorkspacePreset;
      presetAvailability: CreateTaskWorkspacePresetAvailability;
      detail: CreateTaskWorkspaceDetailState;
      resolution: CreateTaskWorkspaceResolution;
      destination: CreateTaskWorkspaceDestination;
    };

export type CreateTaskNameState =
  | { kind: 'generating'; value: '' }
  | { kind: 'suggested'; value: ''; suggestion: string }
  | {
      kind: 'custom';
      value: string;
      suggestion: string | null;
      validation: CreateTaskValidation;
    }
  | {
      kind: 'generation-error';
      value: '';
      message: string;
      retryable: boolean;
    };

export interface CreateTaskSavedPromptOption {
  id: string;
  title: string;
  preview: string;
  insertionText: string;
}

export type CreateTaskResourceStatus =
  | { kind: 'pending'; message: string | null; progress: number | null }
  | { kind: 'ready'; metadata: string | null }
  | { kind: 'retryable-error'; message: string }
  | { kind: 'terminal-error'; message: string };

export type CreateTaskPromptResource =
  | {
      id: string;
      kind: 'image';
      name: string;
      previewSrc: string | null;
      status: CreateTaskResourceStatus;
    }
  | {
      id: string;
      kind: 'file';
      name: string;
      mentionToken: string;
      status: CreateTaskResourceStatus;
    };

export type CreateTaskPromptEditability =
  | { kind: 'editable' }
  | { kind: 'read-only'; reason: string };

export interface CreateTaskPromptContentState {
  value: string;
  editability: CreateTaskPromptEditability;
  intake: CreateTaskAvailability;
  completionQuery: string;
  savedPrompts: CreateTaskOptionsState<CreateTaskSavedPromptOption>;
  resources: readonly CreateTaskPromptResource[];
}

export interface CreateTaskPromptState extends CreateTaskPromptContentState {
  completionOpen: boolean;
}

export interface CreateTaskTextRange {
  from: number;
  to: number;
}

export interface CreateTaskResourceInsertion {
  baseValue: string;
  range: CreateTaskTextRange;
}

export interface CreateTaskResourceOffer extends CreateTaskResourceInsertion {
  source: 'paste' | 'drop';
  files: readonly File[];
  transferData: Readonly<Record<string, string>>;
  containsOrdinaryText: boolean;
}

export interface CreateTaskAgentOption {
  id: string;
  label: string;
  description: string | null;
  group: 'installed' | 'not-installed';
  artwork?: ReactNode;
  availability: CreateTaskOptionAvailability;
}

export interface CreateTaskModelOption {
  id: string;
  label: string;
  description: string | null;
  contextWindowLabel: string | null;
  speed: number | null;
  intelligence: number | null;
  availability: CreateTaskOptionAvailability;
}

export interface CreateTaskEffortOption {
  id: string;
  label: string;
  description: string;
  availability: CreateTaskOptionAvailability;
}

export type CreateTaskCapabilityToggle =
  | { kind: 'supported'; value: boolean }
  | { kind: 'unsupported'; reason: string };

export interface CreateTaskInterfaceState {
  value: 'tui' | 'gui';
  availability: Readonly<Record<'tui' | 'gui', CreateTaskAvailability>>;
}

export interface CreateTaskRunState {
  agent: CreateTaskSearchChoice<CreateTaskAgentOption>;
  model: CreateTaskSearchChoice<CreateTaskModelOption>;
  effort: CreateTaskChoice<CreateTaskEffortOption>;
  autoApprove: CreateTaskCapabilityToggle;
  conversationInterface: CreateTaskInterfaceState;
}

export type CreateTaskWorkspaceFocusTarget =
  | 'preset'
  | 'source-branch'
  | 'branch-name'
  | 'existing-workspace'
  | 'destination';

export type CreateTaskBlockerTarget =
  | { kind: 'project' }
  | { kind: 'create-from' }
  | {
      kind: 'workspace-settings';
      control: CreateTaskWorkspaceFocusTarget;
    }
  | { kind: 'task-name' }
  | { kind: 'prompt' }
  | { kind: 'agent' }
  | { kind: 'model' }
  | { kind: 'effort' }
  | {
      kind: 'capability';
      control: 'auto-approve' | 'tui' | 'gui' | 'attachment';
    }
  | { kind: 'resource'; resourceId: string };

export interface CreateTaskBlocker {
  id: string;
  message: string;
  target: CreateTaskBlockerTarget;
}

export type CreateTaskCreateState =
  | { kind: 'available' }
  | { kind: 'unavailable'; blockers: CreateTaskNonEmpty<CreateTaskBlocker> };

export interface CreateTaskModalState {
  overlay: CreateTaskOverlay;
  project: CreateTaskProjectState;
  origin: CreateTaskOriginState;
  workspace: CreateTaskWorkspaceState;
  taskName: CreateTaskNameState;
  prompt: CreateTaskPromptContentState;
  run: CreateTaskRunState;
  create: CreateTaskCreateState;
  announcements: CreateTaskAnnouncements;
}

export type CreateTaskPromptIntent =
  | {
      type: 'prompt.changed';
      value: string;
      removedResourceIds: readonly string[];
    }
  | { type: 'prompt.completion-open-changed'; open: boolean }
  | { type: 'prompt.completion-query-changed'; query: string }
  | { type: 'prompt.saved-prompts-retry-requested' }
  | {
      type: 'prompt.saved-prompt-selected';
      promptId: string;
      nextValue: string;
    }
  | { type: 'prompt.resources-offered'; offer: CreateTaskResourceOffer }
  | { type: 'prompt.resource-remove-requested'; resourceId: string }
  | { type: 'prompt.resource-retry-requested'; resourceId: string }
  | { type: 'prompt.image-view-requested'; resourceId: string }
  | { type: 'prompt.create-attempted' };

export type CreateTaskWorkspaceRetryTarget =
  | 'detail'
  | 'destination'
  | 'source-branches'
  | 'existing-workspaces';

export type CreateTaskModalIntent =
  | Exclude<
      CreateTaskPromptIntent,
      { type: 'prompt.create-attempted' } | { type: 'prompt.completion-open-changed' }
    >
  | { type: 'overlay.changed'; overlay: CreateTaskOverlay }
  | { type: 'project.query-changed'; query: string }
  | { type: 'project.selected'; projectId: string }
  | { type: 'project.retry-requested' }
  | { type: 'project.add-requested' }
  | { type: 'origin.kind-changed'; kind: CreateTaskOriginKind }
  | {
      type: 'origin.query-changed';
      kind: CreateTaskOriginKind;
      query: string;
    }
  | { type: 'origin.issue-provider-selected'; providerId: string }
  | {
      type: 'origin.pull-request-status-changed';
      status: 'open' | 'closed';
    }
  | {
      type: 'origin.selected';
      origin:
        | { kind: 'branch'; id: string }
        | { kind: 'issue'; id: string }
        | { kind: 'pull-request'; id: string };
    }
  | { type: 'origin.cleared' }
  | { type: 'origin.results-retry-requested'; kind: CreateTaskOriginKind }
  | { type: 'origin.providers-retry-requested' }
  | { type: 'origin.manage-integrations-requested' }
  | { type: 'workspace.preset-changed'; preset: CreateTaskWorkspacePreset }
  | { type: 'workspace.worktree-mode-changed'; mode: 'checkout' | 'create' }
  | { type: 'workspace.source-branch-query-changed'; query: string }
  | { type: 'workspace.source-branch-selected'; branchId: string }
  | { type: 'workspace.existing-query-changed'; query: string }
  | { type: 'workspace.existing-selected'; workspaceId: string }
  | { type: 'workspace.branch-name-changed'; value: string }
  | { type: 'workspace.branch-name-reset-requested' }
  | { type: 'workspace.push-branch-changed'; value: boolean }
  | { type: 'workspace.reuse-conflict-requested'; workspaceId: string }
  | { type: 'workspace.setup-expanded-changed'; expanded: boolean }
  | {
      type: 'workspace.retry-requested';
      target: CreateTaskWorkspaceRetryTarget;
    }
  | {
      type: 'task-name.changed';
      value: string;
      wasTruncated: boolean;
    }
  | { type: 'task-name.generation-retry-requested' }
  | { type: 'run.agent-query-changed'; query: string }
  | { type: 'run.agent-selected'; agentId: string }
  | { type: 'run.agent-retry-requested' }
  | { type: 'run.model-query-changed'; query: string }
  | { type: 'run.model-selected'; modelId: string }
  | { type: 'run.model-retry-requested' }
  | { type: 'run.effort-selected'; effortId: string }
  | { type: 'run.effort-retry-requested' }
  | { type: 'run.auto-approve-changed'; value: boolean }
  | {
      type: 'run.conversation-interface-changed';
      value: 'tui' | 'gui';
    }
  | {
      type: 'prompt.attachment-picker-requested';
      insertion: CreateTaskResourceInsertion;
    }
  | { type: 'create.requested' };

export interface CreateTaskPromptProps {
  state: CreateTaskPromptState;
  onIntent: (intent: CreateTaskPromptIntent) => void;
}

export interface CreateTaskPromptHandle {
  focus(): void;
  getInsertion(): CreateTaskResourceInsertion;
}

export interface CreateTaskModalProps {
  state: CreateTaskModalState;
  onIntent: (intent: CreateTaskModalIntent) => void;
}

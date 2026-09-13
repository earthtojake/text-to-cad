import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { CreateTaskModal } from './create-task-modal';
import {
  createReadyCreateTaskState,
  fixtureAgent,
  fixtureBranch,
  fixtureEffort,
  fixtureIssue,
  fixtureModel,
  fixtureProject,
  fixturePullRequest,
} from './create-task-modal.fixtures';
import type {
  CreateTaskModalIntent,
  CreateTaskModalState,
  CreateTaskPromptResource,
} from './create-task-modal.types';

const meta = {
  title: 'Patterns/CreateTaskModal',
  component: CreateTaskModal,
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <div style={{ width: 672, maxWidth: 'calc(100vw - 32px)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof CreateTaskModal>;

export default meta;
type Story = StoryObj<typeof meta>;

function options<T>(state: { options: { kind: string; items?: readonly T[] } }): readonly T[] {
  return 'items' in state.options ? (state.options.items ?? []) : [];
}

function updateState(
  state: CreateTaskModalState,
  intent: CreateTaskModalIntent
): CreateTaskModalState {
  switch (intent.type) {
    case 'overlay.changed':
      return { ...state, overlay: intent.overlay };
    case 'project.query-changed':
      return { ...state, project: { ...state.project, query: intent.query } };
    case 'project.selected': {
      const project = options(state.project).find(
        (candidate) => (candidate as { id: string }).id === intent.projectId
      );
      return project
        ? {
            ...state,
            overlay: { kind: 'none' },
            project: { ...state.project, selection: { kind: 'selected', option: project } },
          }
        : state;
    }
    case 'origin.kind-changed':
      return { ...state, origin: { ...state.origin, activeKind: intent.kind } };
    case 'origin.query-changed': {
      const key = intent.kind === 'pull-request' ? 'pullRequest' : intent.kind;
      const region = state.origin[key];
      return region.kind === 'available'
        ? {
            ...state,
            origin: {
              ...state.origin,
              [key]: { ...region, query: intent.query },
            },
          }
        : state;
    }
    case 'origin.selected': {
      const origin =
        intent.origin.kind === 'branch'
          ? { kind: 'branch' as const, option: fixtureBranch }
          : intent.origin.kind === 'issue'
            ? { kind: 'issue' as const, option: fixtureIssue }
            : { kind: 'pull-request' as const, option: fixturePullRequest };
      return {
        ...state,
        overlay: { kind: 'none' },
        origin: {
          ...state.origin,
          selection: { kind: 'linked', origin, validation: { kind: 'valid' } },
        },
      };
    }
    case 'origin.cleared':
      return { ...state, origin: { ...state.origin, selection: { kind: 'unlinked' } } };
    case 'workspace.preset-changed':
      return state.workspace.kind === 'inspectable'
        ? {
            ...state,
            workspace: {
              ...state.workspace,
              selectedPreset: intent.preset,
              detail: { kind: 'resolving', preset: intent.preset },
              resolution: { kind: 'resolving' },
              destination: { kind: 'resolving' },
            },
          }
        : state;
    case 'workspace.source-branch-query-changed':
    case 'workspace.existing-query-changed': {
      if (state.workspace.kind !== 'inspectable' || state.workspace.detail.kind !== 'ready') {
        return state;
      }
      const detail = state.workspace.detail.detail;
      if (
        intent.type === 'workspace.source-branch-query-changed' &&
        detail.preset === 'new-worktree'
      ) {
        return {
          ...state,
          workspace: {
            ...state.workspace,
            detail: {
              kind: 'ready',
              detail: {
                ...detail,
                sourceBranch: { ...detail.sourceBranch, query: intent.query },
              },
            },
          },
        };
      }
      if (intent.type === 'workspace.existing-query-changed' && detail.preset === 'use-existing') {
        return {
          ...state,
          workspace: {
            ...state.workspace,
            detail: {
              kind: 'ready',
              detail: {
                ...detail,
                workspace: { ...detail.workspace, query: intent.query },
              },
            },
          },
        };
      }
      return state;
    }
    case 'task-name.changed':
      return {
        ...state,
        taskName: {
          kind: 'custom',
          value: intent.value,
          suggestion:
            state.taskName.kind === 'suggested' || state.taskName.kind === 'custom'
              ? state.taskName.suggestion
              : null,
          validation: { kind: 'valid' },
        },
      };
    case 'prompt.changed':
      return { ...state, prompt: { ...state.prompt, value: intent.value } };
    case 'prompt.completion-query-changed':
      return {
        ...state,
        prompt: { ...state.prompt, completionQuery: intent.query },
      };
    case 'prompt.saved-prompt-selected':
      return {
        ...state,
        overlay: { kind: 'none' },
        prompt: { ...state.prompt, value: intent.nextValue },
      };
    case 'prompt.resource-remove-requested':
      return {
        ...state,
        prompt: {
          ...state.prompt,
          resources: state.prompt.resources.filter((resource) => resource.id !== intent.resourceId),
        },
      };
    case 'run.agent-query-changed':
      return {
        ...state,
        run: { ...state.run, agent: { ...state.run.agent, query: intent.query } },
      };
    case 'run.agent-selected':
      return {
        ...state,
        overlay: { kind: 'none' },
        run: {
          ...state.run,
          agent: { ...state.run.agent, selection: { kind: 'selected', option: fixtureAgent } },
        },
      };
    case 'run.model-query-changed':
      return {
        ...state,
        run: { ...state.run, model: { ...state.run.model, query: intent.query } },
      };
    case 'run.model-selected':
      return {
        ...state,
        overlay: { kind: 'none' },
        run: {
          ...state.run,
          model: { ...state.run.model, selection: { kind: 'selected', option: fixtureModel } },
        },
      };
    case 'run.effort-selected':
      return {
        ...state,
        overlay: { kind: 'none' },
        run: {
          ...state.run,
          effort: { ...state.run.effort, selection: { kind: 'selected', option: fixtureEffort } },
        },
      };
    case 'run.auto-approve-changed':
      return {
        ...state,
        run: {
          ...state.run,
          autoApprove: { kind: 'supported', value: intent.value },
        },
      };
    case 'run.conversation-interface-changed':
      return {
        ...state,
        run: {
          ...state.run,
          conversationInterface: { ...state.run.conversationInterface, value: intent.value },
        },
      };
    default:
      return state;
  }
}

function ControlledModal({ initial }: { initial: CreateTaskModalState }) {
  const [state, setState] = useState(initial);
  return (
    <CreateTaskModal
      state={state}
      onIntent={(intent) => setState((current) => updateState(current, intent))}
    />
  );
}

function story(initial: CreateTaskModalState): Story {
  return {
    args: { state: initial, onIntent: () => {} },
    render: () => <ControlledModal initial={initial} />,
  };
}

export const Ready = story(createReadyCreateTaskState());

const projectOpen = createReadyCreateTaskState();
projectOpen.overlay = { kind: 'project' };
export const ProjectPicker = story(projectOpen);

const projectLoading = createReadyCreateTaskState();
projectLoading.overlay = { kind: 'project' };
projectLoading.project.options = { kind: 'loading' };
export const ProjectLoading = story(projectLoading);

const projectEmpty = createReadyCreateTaskState();
projectEmpty.overlay = { kind: 'project' };
projectEmpty.project.selection = { kind: 'none' };
projectEmpty.project.options = { kind: 'empty' };
export const NoProjects = story(projectEmpty);

const projectStale = createReadyCreateTaskState();
projectStale.overlay = { kind: 'project' };
projectStale.project.options = {
  kind: 'stale-error',
  items: [fixtureProject],
  message: 'Projects could not be refreshed.',
  retryable: true,
};
export const ProjectStale = story(projectStale);

const createFrom = createReadyCreateTaskState();
createFrom.overlay = { kind: 'create-from', nested: 'none' };
export const CreateFromBranch = story(createFrom);

const issueOrigin = createReadyCreateTaskState();
issueOrigin.overlay = { kind: 'create-from', nested: 'none' };
issueOrigin.origin.activeKind = 'issue';
export const CreateFromIssue = story(issueOrigin);

const unsupportedOrigin = createReadyCreateTaskState();
unsupportedOrigin.overlay = { kind: 'create-from', nested: 'none' };
unsupportedOrigin.origin.activeKind = 'issue';
unsupportedOrigin.origin.issue = {
  kind: 'unsupported',
  reason: 'Issue integrations are not available for this Project.',
};
export const CreateFromUnsupported = story(unsupportedOrigin);

const issueProviderError = createReadyCreateTaskState();
issueProviderError.overlay = { kind: 'create-from', nested: 'none' };
issueProviderError.origin.activeKind = 'issue';
if (issueProviderError.origin.issue.kind === 'available') {
  issueProviderError.origin.issue.provider = {
    ...issueProviderError.origin.issue.provider,
    selection: { kind: 'none' },
    options: {
      kind: 'error',
      message: 'Issue providers could not be loaded.',
      retryable: true,
    },
  };
}
export const IssueProviderRecovery = story(issueProviderError);

const pullRequestOrigin = createReadyCreateTaskState();
pullRequestOrigin.overlay = { kind: 'create-from', nested: 'pull-request-status' };
pullRequestOrigin.origin.activeKind = 'pull-request';
export const CreateFromPullRequest = story(pullRequestOrigin);

const workspace = createReadyCreateTaskState();
workspace.overlay = { kind: 'workspace-settings', nested: 'none' };
export const WorkspaceSettings = story(workspace);

const workspaceFallback = createReadyCreateTaskState();
workspaceFallback.overlay = { kind: 'workspace-settings', nested: 'none' };
if (workspaceFallback.workspace.kind === 'inspectable') {
  workspaceFallback.workspace.destination = {
    kind: 'fallback',
    path: '/tmp/emdash/worktrees',
    configuredPath: '/Volumes/team/worktrees',
    warning: 'The configured destination is unavailable, so the local fallback will be used.',
  };
  workspaceFallback.workspace.resolution = {
    kind: 'ready-warning',
    message: 'Using a fallback destination.',
  };
}
export const WorkspaceFallback = story(workspaceFallback);

const workspaceDestinationUnavailable = createReadyCreateTaskState();
workspaceDestinationUnavailable.overlay = { kind: 'workspace-settings', nested: 'none' };
if (workspaceDestinationUnavailable.workspace.kind === 'inspectable') {
  workspaceDestinationUnavailable.workspace.destination = {
    kind: 'unavailable',
    reason: 'No writable Workspace destination is available.',
  };
  workspaceDestinationUnavailable.workspace.resolution = {
    kind: 'invalid',
    message: 'Choose a writable destination.',
  };
}
export const WorkspaceDestinationUnavailable = story(workspaceDestinationUnavailable);

const newWorktree = createReadyCreateTaskState();
newWorktree.overlay = { kind: 'workspace-settings', nested: 'source-branch' };
newWorktree.workspace = {
  kind: 'inspectable',
  selectedPreset: 'new-worktree',
  presetAvailability: {
    'new-worktree': { kind: 'available' },
    'repo-root': { kind: 'available' },
    'use-existing': { kind: 'available' },
    'checkout-pr': { kind: 'unavailable', reason: 'Link a Pull Request first.' },
    'pr-new-branch': { kind: 'unavailable', reason: 'Link a Pull Request first.' },
  },
  detail: {
    kind: 'ready',
    detail: {
      preset: 'new-worktree',
      mode: 'create',
      sourceBranch: {
        availability: { kind: 'available' },
        query: '',
        selection: { kind: 'selected', option: fixtureBranch },
        options: { kind: 'ready', items: [fixtureBranch] },
      },
      branchName: {
        value: 'feat/create-task',
        generatedValue: 'feat/create-task',
        source: 'derived',
        validation: { kind: 'valid' },
      },
      pushBranch: { kind: 'supported', value: true },
      setup: {
        expanded: true,
        steps: [
          { id: 'prepare', label: 'Prepare Workspace', description: 'pnpm install' },
          { id: 'setup', label: 'Run setup', description: 'pnpm run build' },
        ],
      },
    },
  },
  resolution: { kind: 'ready-valid' },
  destination: {
    kind: 'ready',
    path: '~/Code/emdash-worktrees/feat-create-task',
    description: 'New worktree',
  },
};
export const NewWorktreeSettings = story(newWorktree);

const existingWorkspaceLoading = createReadyCreateTaskState();
existingWorkspaceLoading.overlay = { kind: 'workspace-settings', nested: 'existing-workspace' };
if (existingWorkspaceLoading.workspace.kind === 'inspectable') {
  existingWorkspaceLoading.workspace.selectedPreset = 'use-existing';
  existingWorkspaceLoading.workspace.detail = {
    kind: 'ready',
    detail: {
      preset: 'use-existing',
      workspace: {
        availability: { kind: 'available' },
        query: '',
        selection: { kind: 'none' },
        options: { kind: 'loading' },
      },
    },
  };
}
export const ExistingWorkspaceLoading = story(existingWorkspaceLoading);

const checkoutPullRequest = createReadyCreateTaskState();
checkoutPullRequest.overlay = { kind: 'workspace-settings', nested: 'none' };
checkoutPullRequest.origin.selection = {
  kind: 'linked',
  origin: { kind: 'pull-request', option: fixturePullRequest },
  validation: { kind: 'valid' },
};
checkoutPullRequest.workspace = {
  kind: 'inspectable',
  selectedPreset: 'checkout-pr',
  presetAvailability: {
    'new-worktree': { kind: 'available' },
    'repo-root': { kind: 'available' },
    'use-existing': { kind: 'available' },
    'checkout-pr': { kind: 'available' },
    'pr-new-branch': { kind: 'available' },
  },
  detail: {
    kind: 'ready',
    detail: {
      preset: 'checkout-pr',
      pullRequest: fixturePullRequest,
      setup: { expanded: false, steps: [] },
    },
  },
  resolution: { kind: 'ready-valid' },
  destination: {
    kind: 'ready',
    path: '~/Code/emdash-worktrees/pr-128',
    description: 'Pull Request worktree',
  },
};
export const CheckoutPullRequestSettings = story(checkoutPullRequest);

const branchFromPullRequest = createReadyCreateTaskState();
branchFromPullRequest.overlay = { kind: 'workspace-settings', nested: 'none' };
branchFromPullRequest.origin.selection = checkoutPullRequest.origin.selection;
branchFromPullRequest.workspace = {
  ...checkoutPullRequest.workspace,
  selectedPreset: 'pr-new-branch',
  detail: {
    kind: 'ready',
    detail: {
      preset: 'pr-new-branch',
      pullRequest: fixturePullRequest,
      branchName: {
        value: 'feat/follow-up',
        generatedValue: 'feat/follow-up',
        source: 'derived',
        validation: { kind: 'valid' },
      },
      pushBranch: { kind: 'supported', value: true },
      setup: { expanded: false, steps: [] },
    },
  },
};
export const BranchFromPullRequestSettings = story(branchFromPullRequest);

const workspaceError = createReadyCreateTaskState();
workspaceError.overlay = { kind: 'workspace-settings', nested: 'none' };
if (workspaceError.workspace.kind === 'inspectable') {
  workspaceError.workspace.detail = {
    kind: 'unavailable',
    preset: 'use-existing',
    reason: 'Existing Workspaces could not be inspected.',
    recoverable: true,
  };
  workspaceError.workspace.resolution = {
    kind: 'recoverably-unavailable',
    reason: 'Existing Workspaces could not be inspected.',
  };
}
export const WorkspaceRecovery = story(workspaceError);

const resources: CreateTaskPromptResource[] = [
  {
    id: 'image-ready',
    kind: 'image',
    name: 'reference.png',
    previewSrc: 'https://placehold.co/128x96/27272a/e4e4e7?text=UI',
    status: { kind: 'ready', metadata: '128 × 96' },
  },
  {
    id: 'file-pending',
    kind: 'file',
    name: 'requirements.md',
    mentionToken: '@requirements.md',
    status: { kind: 'pending', message: 'Indexing…', progress: null },
  },
  {
    id: 'image-error',
    kind: 'image',
    name: 'broken.png',
    previewSrc: null,
    status: { kind: 'retryable-error', message: 'Upload failed' },
  },
];
const promptResources = createReadyCreateTaskState();
promptResources.prompt.value = 'Implement the requested design using @requirements.md';
promptResources.prompt.resources = resources;
promptResources.prompt.savedPrompts = {
  kind: 'ready',
  items: [
    {
      id: 'review',
      title: 'Review this change',
      preview: 'Review the current changes for correctness.',
      insertionText: 'Review the current changes for correctness.',
    },
  ],
};
export const PromptResources = story(promptResources);

const savedPromptError = createReadyCreateTaskState();
savedPromptError.overlay = { kind: 'saved-prompts' };
savedPromptError.prompt.savedPrompts = {
  kind: 'error',
  message: 'Saved Prompts could not be loaded.',
  retryable: true,
};
export const SavedPromptRecovery = story(savedPromptError);

const savedPromptStale = createReadyCreateTaskState();
savedPromptStale.overlay = { kind: 'saved-prompts' };
savedPromptStale.prompt.savedPrompts = {
  kind: 'stale-error',
  items: [
    {
      id: 'review',
      title: 'Review this change',
      preview: 'Review the current changes for correctness.',
      insertionText: 'Review the current changes for correctness.',
    },
  ],
  message: 'Saved Prompts could not be refreshed.',
  retryable: true,
};
export const SavedPromptStale = story(savedPromptStale);

const taskNameGenerationError = createReadyCreateTaskState();
taskNameGenerationError.taskName = {
  kind: 'generation-error',
  value: '',
  message: 'Task name generation failed.',
  retryable: true,
};
export const TaskNameGenerationError = story(taskNameGenerationError);

const unavailableCapabilities = createReadyCreateTaskState();
unavailableCapabilities.run.autoApprove = {
  kind: 'unsupported',
  reason: 'This Agent does not support auto-approve.',
};
unavailableCapabilities.run.conversationInterface = {
  ...unavailableCapabilities.run.conversationInterface,
  availability: {
    ...unavailableCapabilities.run.conversationInterface.availability,
    tui: {
      kind: 'unavailable',
      reason: 'This Agent only supports GUI conversations.',
    },
  },
};
unavailableCapabilities.prompt.intake = {
  kind: 'unavailable',
  reason: 'Attachments are not supported by this Agent.',
};
export const UnavailableCapabilities = story(unavailableCapabilities);

const blocked = createReadyCreateTaskState();
blocked.project.selection = { kind: 'none' };
blocked.create = {
  kind: 'unavailable',
  blockers: [
    { id: 'project', message: 'Select a Project.', target: { kind: 'project' } },
    { id: 'prompt', message: 'Enter a Prompt.', target: { kind: 'prompt' } },
  ],
};
export const GuardedCreate = story(blocked);

const remoteProject = createReadyCreateTaskState();
remoteProject.project.selection = {
  kind: 'selected',
  option: {
    ...fixtureProject,
    id: 'remote',
    label: 'Remote Emdash',
    path: '/srv/emdash',
    location: { kind: 'ssh', hostLabel: 'build-machine' },
  },
};
export const RemoteProject = story(remoteProject);

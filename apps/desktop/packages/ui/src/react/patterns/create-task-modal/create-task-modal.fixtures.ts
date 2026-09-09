import type {
  CreateTaskAgentOption,
  CreateTaskBranchOption,
  CreateTaskEffortOption,
  CreateTaskIssueOption,
  CreateTaskIssueProviderOption,
  CreateTaskModalState,
  CreateTaskModelOption,
  CreateTaskProjectOption,
  CreateTaskPullRequestOption,
} from './create-task-modal.types';

const available = { kind: 'available' } as const;

export const fixtureProject: CreateTaskProjectOption = {
  id: 'emdash',
  label: 'Emdash',
  path: '~/Code/emdash',
  location: { kind: 'local' },
  availability: available,
};

export const fixtureBranch: CreateTaskBranchOption = {
  id: 'main',
  label: 'main',
  description: 'Default branch',
  isDefault: true,
  availability: available,
};

export const fixtureIssueProvider: CreateTaskIssueProviderOption = {
  id: 'linear',
  label: 'Linear',
  availability: available,
};

export const fixtureIssue: CreateTaskIssueOption = {
  id: 'issue-241',
  providerId: 'linear',
  identifier: 'EMD-241',
  title: 'Improve Create Task',
  stateLabel: 'In progress',
  availability: available,
};

export const fixturePullRequest: CreateTaskPullRequestOption = {
  id: 'pr-128',
  number: '128',
  title: 'Improve Create Task',
  headBranch: 'feat/create-task',
  status: 'open',
  availability: available,
};

export const fixtureAgent: CreateTaskAgentOption = {
  id: 'claude-code',
  label: 'Claude Code',
  description: 'Anthropic coding agent',
  group: 'installed',
  availability: available,
};

export const fixtureModel: CreateTaskModelOption = {
  id: 'sonnet',
  label: 'Sonnet',
  description: 'Balanced model',
  contextWindowLabel: '200K',
  speed: 0.7,
  intelligence: 0.8,
  availability: available,
};

export const fixtureEffort: CreateTaskEffortOption = {
  id: 'high',
  label: 'High',
  description: 'Spend more time reasoning',
  availability: available,
};

export function createReadyCreateTaskState(): CreateTaskModalState {
  return {
    overlay: { kind: 'none' },
    project: {
      query: '',
      selection: { kind: 'selected', option: fixtureProject },
      options: { kind: 'ready', items: [fixtureProject] },
    },
    origin: {
      activeKind: 'branch',
      selection: { kind: 'unlinked' },
      branch: { kind: 'available', query: '', options: { kind: 'ready', items: [fixtureBranch] } },
      issue: {
        kind: 'available',
        query: '',
        provider: {
          availability: available,
          selection: { kind: 'selected', option: fixtureIssueProvider },
          options: { kind: 'ready', items: [fixtureIssueProvider] },
        },
        options: { kind: 'ready', items: [fixtureIssue] },
      },
      pullRequest: {
        kind: 'available',
        query: '',
        status: 'open',
        options: { kind: 'ready', items: [fixturePullRequest] },
      },
    },
    workspace: {
      kind: 'inspectable',
      selectedPreset: 'repo-root',
      presetAvailability: {
        'new-worktree': available,
        'repo-root': available,
        'use-existing': available,
        'checkout-pr': { kind: 'unavailable', reason: 'Link a Pull Request first.' },
        'pr-new-branch': { kind: 'unavailable', reason: 'Link a Pull Request first.' },
      },
      detail: {
        kind: 'ready',
        detail: {
          preset: 'repo-root',
          repositoryPath: '~/Code/emdash',
          consequence: 'Work directly in the repository directory.',
        },
      },
      resolution: { kind: 'ready-valid' },
      destination: {
        kind: 'ready',
        path: '~/Code/emdash',
        description: 'Repository directory',
      },
    },
    taskName: { kind: 'suggested', value: '', suggestion: 'improve-create-task' },
    prompt: {
      value: '',
      editability: { kind: 'editable' },
      intake: available,
      completionQuery: '',
      savedPrompts: { kind: 'empty' },
      resources: [],
    },
    run: {
      agent: {
        availability: available,
        query: '',
        selection: { kind: 'selected', option: fixtureAgent },
        options: { kind: 'ready', items: [fixtureAgent] },
      },
      model: {
        availability: available,
        query: '',
        selection: { kind: 'selected', option: fixtureModel },
        options: { kind: 'ready', items: [fixtureModel] },
      },
      effort: {
        availability: available,
        selection: { kind: 'selected', option: fixtureEffort },
        options: { kind: 'ready', items: [fixtureEffort] },
      },
      autoApprove: { kind: 'supported', value: false },
      conversationInterface: {
        value: 'gui',
        availability: { tui: available, gui: available },
      },
    },
    create: { kind: 'available' },
    announcements: { polite: null, assertive: null },
  };
}

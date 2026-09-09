import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { HomeMainPanel } from './home-view';

const mocks = vi.hoisted(() => ({
  projects: new Map([
    ['project-1', { id: 'project-1', name: 'Bridge' }],
    ['project-2', { id: 'project-2', name: 'Vehicle' }],
  ]),
  startChat: vi.fn(),
  openProject: vi.fn(),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', async (importOriginal) => ({
  ...(await importOriginal()),
  firstAvailableProjectId: () => 'project-1',
  getProjectManagerStore: () => ({ projects: mocks.projects }),
  getProjectSshConnectionId: () => undefined,
  projectDisplayName: (project: { name: string }) => project.name,
  projectViewKind: () => 'ready',
}));

vi.mock('@core/features/projects/browser/open-project-folder', () => ({
  useOpenProjectFolder: () => ({ open: mocks.openProject, busy: false }),
}));

vi.mock('./new-chat-agent-model-selector', () => ({
  NewChatAgentModelSelector: ({
    providerId,
    modelId,
    onModelChange,
  }: {
    providerId: string | null;
    modelId: string | null;
    onModelChange: (modelId: string | null) => void;
  }) => (
    <div>
      <button type="button" aria-label="Choose agent and model">
        {providerId ?? 'Choose agent'} · {modelId ?? 'Default'}
      </button>
      <button
        type="button"
        aria-label="Test GPT-5.6 Sol"
        onClick={() => onModelChange('gpt-5.6-sol')}
      >
        Test GPT-5.6 Sol
      </button>
    </div>
  ),
}));

vi.mock('@core/features/tasks/contributions/browser', () => ({
  tasksBrowserContributions: {
    useStartBlankChat: () => ({
      start: mocks.startChat,
      busy: false,
      disabled: false,
      providerId: 'codex',
      installedProviderIds: ['codex', 'claude'],
      setProvider: vi.fn(),
    }),
  },
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useViewParams: () => ({ projectId: 'project-1' }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('HomeMainPanel new chat draft', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.startChat.mockReset();
    mocks.startChat.mockResolvedValue({ taskId: 'task-1', conversationId: 'conversation-1' });
    mocks.openProject.mockReset();
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('does not persist a task until the first message is sent', async () => {
    await act(async () => root.render(<HomeMainPanel />));

    expect(mocks.startChat).not.toHaveBeenCalled();
    expect(findButton(host, 'Choose project').textContent).toContain('Bridge');

    await act(async () => {
      setTextareaValue(host.querySelector('textarea')!, 'Make a mounting bracket');
    });
    await act(async () => findButton(host, 'Send message').click());

    expect(mocks.startChat).toHaveBeenCalledOnce();
    expect(mocks.startChat).toHaveBeenCalledWith('project-1', 'Make a mounting bracket', undefined);
  });

  it('starts the chat with the selected named model', async () => {
    await act(async () => root.render(<HomeMainPanel />));

    await act(async () => findButton(host, 'Test GPT-5.6 Sol').click());
    await act(async () => {
      setTextareaValue(host.querySelector('textarea')!, 'Make a mounting bracket');
    });
    await act(async () => findButton(host, 'Send message').click());

    expect(mocks.startChat).toHaveBeenCalledWith(
      'project-1',
      'Make a mounting bracket',
      'gpt-5.6-sol'
    );
  });
});

function setTextareaValue(textarea: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  setter?.call(textarea, value);
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

function findButton(host: HTMLElement, accessibleName: string): HTMLButtonElement {
  const button = Array.from(host.querySelectorAll('button')).find(
    (candidate) => candidate.getAttribute('aria-label') === accessibleName
  );
  if (!button) throw new Error(`Could not find ${accessibleName} button`);
  return button;
}

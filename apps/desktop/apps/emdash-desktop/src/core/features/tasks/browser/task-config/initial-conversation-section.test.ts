import type { ChatComposerProps, PromptEditorRef } from '@emdash/ui/react/components';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  InitialConversationField,
  useInitialConversationState,
  type InitialConversationState,
} from '@core/features/tasks/contributions/browser/task-config/initial-conversation-section';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const mocks = vi.hoisted(() => ({
  getProjectSshConnectionId: vi.fn(),
  setProviderOverride: vi.fn(),
  editorText: '',
  editorApi: {
    focus: vi.fn(),
    clear: vi.fn(),
    getText: vi.fn(() => mocks.editorText),
    setText: vi.fn((text: string) => {
      mocks.editorText = text;
    }),
    insertMention: vi.fn(),
    prependMention: vi.fn(),
    removeMention: vi.fn(),
    setMentionPending: vi.fn(),
  },
  lastChatComposerProps: null as unknown,
}));

vi.mock('@emdash/ui/react/components', () => ({
  ChatComposer: (props: unknown) => {
    mocks.lastChatComposerProps = props;
    const { editorApiRef } = props as { editorApiRef?: React.Ref<PromptEditorRef> };
    if (typeof editorApiRef === 'function') {
      editorApiRef(mocks.editorApi as unknown as PromptEditorRef);
    } else if (editorApiRef) {
      editorApiRef.current = mocks.editorApi as unknown as PromptEditorRef;
    }
    return null;
  },
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  getProjectSshConnectionId: mocks.getProjectSshConnectionId,
  asAvailableProject: vi.fn(() => undefined),
  getProjectStore: vi.fn(() => undefined),
  getProjectViewStore: vi.fn(() => undefined),
}));

vi.mock('@core/features/library/api/browser/prompts/use-prompt-library', () => ({
  usePromptLibrary: () => ({ value: [] }),
}));

vi.mock('@core/features/agents/contributions/browser/agent-selector', () => ({
  AgentSelector: () => null,
}));

vi.mock('../create-task-modal/use-prompt-file-drop', () => ({
  usePromptFileDrop: () => ({ isDragOver: false, dropHandlers: {} }),
}));

vi.mock('../context-bar/add-context-popover', () => ({
  AddContextPopover: () => null,
}));

vi.mock('@core/features/agents/api/browser/use-agents', () => ({
  useAgents: () => ({
    data: [
      {
        id: 'claude',
        capabilities: {
          acp: { kind: 'supported' },
          autoApprove: { kind: 'supported' },
          models: { kind: 'none' },
        },
      },
    ],
  }),
}));

vi.mock('@core/primitives/logging/browser/logger', () => ({
  log: { warn: vi.fn() },
}));

vi.mock('@core/features/conversations/api/browser/use-effective-provider', () => ({
  useEffectiveProvider: () => ({
    providerId: 'claude',
    setProviderOverride: mocks.setProviderOverride,
    createDisabled: false,
  }),
}));

type InitialConversationOptions = Parameters<typeof useInitialConversationState>[3];

let latestState: InitialConversationState | undefined;

function Probe({
  projectId,
  options,
}: {
  projectId: string;
  options?: InitialConversationOptions;
}) {
  latestState = useInitialConversationState(projectId, undefined, false, options);
  return null;
}

function FieldProbe({
  linkedIssue,
  includeIssueContextByDefault = false,
  placeholder,
}: {
  linkedIssue?: LinkedIssue;
  includeIssueContextByDefault?: boolean;
  placeholder?: string;
}) {
  const state = useInitialConversationState('project-1');
  const [queryClient] = React.useState(() => new QueryClient());
  return React.createElement(
    QueryClientProvider,
    { client: queryClient },
    React.createElement(InitialConversationField, {
      state,
      linkedIssue,
      includeIssueContextByDefault,
      placeholder,
    })
  );
}

function chatComposerProps(): ChatComposerProps {
  if (!mocks.lastChatComposerProps) {
    throw new Error('ChatComposer was not rendered');
  }
  return mocks.lastChatComposerProps as ChatComposerProps;
}

describe('useInitialConversationState', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    latestState = undefined;
    mocks.editorText = '';
    mocks.lastChatComposerProps = null;
    mocks.getProjectSshConnectionId.mockReturnValue(undefined);

    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
      url: 'http://localhost',
    });
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);
    vi.stubGlobal('Event', dom.window.Event);
    vi.stubGlobal('localStorage', dom.window.localStorage);
    dom.window.localStorage.clear();

    container = dom.window.document.getElementById('root') as HTMLDivElement;
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    dom.window.close();
  });

  async function renderProbe(projectId: string, options?: InitialConversationOptions) {
    await act(async () => {
      root.render(React.createElement(Probe, { projectId, options }));
    });
  }

  async function setPrompt(prompt: string) {
    await act(async () => {
      latestState?.setPrompt(prompt);
    });
  }

  it('resets the prompt by default when the project changes', async () => {
    await renderProbe('project-1');
    await setPrompt('Keep this for project one');

    expect(latestState?.prompt).toBe('Keep this for project one');

    await renderProbe('project-2');

    expect(latestState?.prompt).toBe('');
  });

  it('can preserve the prompt when the project changes', async () => {
    await renderProbe('project-1', { resetPromptOnProjectChange: false });
    await setPrompt('Keep this automation prompt');

    expect(latestState?.prompt).toBe('Keep this automation prompt');

    await renderProbe('project-2', { resetPromptOnProjectChange: false });

    expect(latestState?.prompt).toBe('Keep this automation prompt');
  });

  it('persists the auto-approve preference', async () => {
    await renderProbe('project-1');

    await act(async () => {
      latestState?.setAutoApprove(true);
    });

    await act(async () => root.unmount());
    root = createRoot(container);
    await renderProbe('project-2');

    expect(latestState?.autoApprove).toBe(true);
  });

  it('defaults chat UI off when the provider supports ACP', async () => {
    await renderProbe('project-1');

    expect(latestState?.useChatUi).toBe(false);
  });

  it('persists after the user enables chat UI', async () => {
    await renderProbe('project-1');

    await act(async () => {
      latestState?.setUseChatUi(true);
    });

    expect(dom.window.localStorage.getItem('initial-conversation:chat-ui-enabled')).toBe('true');

    await act(async () => root.unmount());
    root = createRoot(container);
    await renderProbe('project-2');

    expect(latestState?.useChatUi).toBe(true);
  });
});

describe('InitialConversationField', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    latestState = undefined;
    mocks.editorText = '';
    mocks.lastChatComposerProps = null;
    mocks.getProjectSshConnectionId.mockReturnValue(undefined);

    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
      url: 'http://localhost',
    });
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);
    vi.stubGlobal('Event', dom.window.Event);
    vi.stubGlobal('localStorage', dom.window.localStorage);
    dom.window.localStorage.clear();

    container = dom.window.document.getElementById('root') as HTMLDivElement;
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    dom.window.close();
  });

  async function renderField(props: React.ComponentProps<typeof FieldProbe> = {}) {
    await act(async () => {
      root.render(React.createElement(FieldProbe, props));
    });
    await act(async () => {});
  }

  it('disables @ mention search while preserving slash commands and placeholder override', async () => {
    await renderField();

    const props = chatComposerProps();
    expect(props.mentionProvider).toBeUndefined();
    expect(props.onMentionInsert).toBeUndefined();
    expect(props.queryMentions).toBeUndefined();
    expect(props.queryCommands).toEqual(expect.any(Function));
    expect(props.placeholder).not.toContain('@');
  });

  it('forwards automation placeholder text without enabling @ mentions', async () => {
    await renderField({ placeholder: 'Add a prompt to the automation...' });

    const props = chatComposerProps();
    expect(props.placeholder).toBe('Add a prompt to the automation...');
    expect(props.mentionProvider).toBeUndefined();
  });

  it('preserves the selected linked issue pill', async () => {
    const linkedIssue: LinkedIssue = {
      provider: 'linear',
      identifier: 'ENG-123',
      displayIdentifier: 'ENG-123',
      title: 'Fix flaky tests',
      url: 'https://linear.app/emdash/issue/ENG-123/fix-flaky-tests',
    };

    await renderField({ linkedIssue, includeIssueContextByDefault: true });

    expect(mocks.editorApi.prependMention).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'issue:linear:ENG-123',
        label: 'issue:linear:ENG-123',
        name: 'ENG-123',
        kind: 'issue',
        description: 'Fix flaky tests',
      })
    );
  });

  it('renders a generic icon for saved issue mentions', async () => {
    const linkedIssue: LinkedIssue = {
      provider: 'linear',
      identifier: 'ENG-123',
      displayIdentifier: 'ENG-123',
      title: 'Fix flaky tests',
      url: 'https://linear.app/emdash/issue/ENG-123/fix-flaky-tests',
    };

    await renderField({ linkedIssue, includeIssueContextByDefault: true });

    const renderMentionIcon = chatComposerProps().renderMentionIcon;
    const firstIcon = renderMentionIcon?.({
      id: 'issue:linear:ENG-123',
      label: 'issue:linear:ENG-123',
      kind: 'issue',
    });
    const secondIcon = renderMentionIcon?.({
      id: 'issue:linear:ENG-456',
      label: 'issue:linear:ENG-456',
      kind: 'issue',
    });

    expect(firstIcon).toMatchObject({ props: { name: 'circle-dot' } });
    expect(secondIcon).toMatchObject({ props: { name: 'circle-dot' } });
  });
});

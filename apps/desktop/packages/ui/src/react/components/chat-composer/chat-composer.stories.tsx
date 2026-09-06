import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { useEffect, useState } from 'react';
import { Box } from '@/react/primitives/box';
import { Button } from '@/react/primitives/button';
import { ChatComposer } from '.';
import type {
  ComposerAgentOption,
  ComposerEffortOption,
  ComposerModelOption,
  ComposerMcpServer,
  ComposerNotice,
  ComposerNoticeVariant,
  ComposerPermissionModeOption,
  ComposerQueuedPrompt,
  ContextUsage,
  ContextMentionProvider,
  MentionItem,
  CommandItem,
} from '.';
import { PermissionBand, type ComposerPermissionRequest } from './permission-band';
import * as s from '@react/story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

const MOCK_MODELS: Record<string, ComposerModelOption> = {
  'claude-opus-4': {
    name: 'Claude Opus 4',
    description: 'Most capable model for complex reasoning and nuanced tasks.',
    modelFeatures: { contextWindowSize: 200_000, speed: 0.4, intelligence: 1 },
  },
  'claude-sonnet-4-5': {
    name: 'Claude Sonnet 4.5',
    description: 'Excellent balance of speed and intelligence for everyday tasks.',
    modelFeatures: { contextWindowSize: 200_000, speed: 0.75, intelligence: 0.85 },
  },
  'gpt-4o': {
    name: 'GPT-4o',
    description: 'OpenAI flagship multimodal model.',
    modelFeatures: { contextWindowSize: 128_000, speed: 0.7, intelligence: 0.9 },
  },
};

function AgentDot({ color }: { color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 16,
        height: 16,
        borderRadius: 4,
        background: color,
        flexShrink: 0,
      }}
    />
  );
}

const MOCK_AGENTS: ComposerAgentOption[] = [
  {
    id: 'claude',
    name: 'Claude',
    icon: <AgentDot color="#d97706" />,
    description: 'Anthropic Claude coding agent.',
    groupLabel: 'Installed',
  },
  {
    id: 'codex',
    name: 'OpenAI Codex',
    icon: <AgentDot color="#10b981" />,
    description: 'OpenAI Codex CLI agent.',
    groupLabel: 'Installed',
  },
  {
    id: 'gemini',
    name: 'Gemini CLI',
    icon: <AgentDot color="#6366f1" />,
    description: 'Google Gemini CLI agent.',
    disabled: true,
    groupLabel: 'Not installed',
  },
];

// ── Mock @ mentions ───────────────────────────────────────────────────────────

const MOCK_FILES: MentionItem[] = [
  {
    id: 'src/components/chat-composer.tsx',
    label: 'src/components/chat-composer.tsx',
    name: 'chat-composer.tsx',
    kind: 'file',
    description: 'UI',
  },
  {
    id: 'src/components/prompt-editor/prompt-editor.tsx',
    label: 'src/components/prompt-editor/prompt-editor.tsx',
    name: 'prompt-editor.tsx',
    kind: 'file',
    description: 'UI',
  },
  {
    id: 'src/lib/file-icons.ts',
    label: 'src/lib/file-icons.ts',
    name: 'file-icons.ts',
    kind: 'file',
  },
  { id: 'package.json', label: 'package.json', name: 'package.json', kind: 'file' },
  { id: 'README.md', label: 'README.md', name: 'README.md', kind: 'file' },
  {
    id: 'issue-42',
    label: 'issue-42',
    name: 'Issue #42: Dark mode toggle',
    kind: 'issue',
    description: 'open',
  },
  {
    id: 'handleSubmit',
    label: 'handleSubmit',
    name: 'handleSubmit()',
    kind: 'symbol',
    description: 'chat-composer.tsx',
  },
];

const mockMentionProvider: ContextMentionProvider = {
  async search(query: string) {
    await new Promise((r) => setTimeout(r, 80));
    const q = query.toLowerCase();
    return q
      ? MOCK_FILES.filter(
          (f) =>
            f.label.toLowerCase().includes(q) ||
            (f.name ?? '').toLowerCase().includes(q) ||
            (f.description ?? '').toLowerCase().includes(q)
        )
      : MOCK_FILES;
  },
};

// ── Mock / commands ───────────────────────────────────────────────────────────

const MOCK_COMMANDS: CommandItem[] = [
  {
    id: 'clear',
    name: 'clear',
    label: 'Clear conversation',
    description: 'Wipe the conversation history.',
    behavior: 'execute',
    section: 'Commands',
  },
  {
    id: 'model',
    name: 'model',
    label: 'Switch model',
    description: 'Change the active model.',
    behavior: 'execute',
    section: 'Commands',
  },
  {
    id: 'help',
    name: 'help',
    label: 'Help',
    description: 'Show available commands.',
    behavior: 'insert',
    section: 'Commands',
  },
  {
    id: 'compact',
    name: 'compact',
    label: 'Compact',
    description: 'Summarize and compact the context.',
    behavior: 'execute',
    section: 'Commands',
  },
  {
    id: 'prompt:review',
    name: 'Review changes',
    label: 'Review changes',
    description: 'Review all changes in this worktree.',
    behavior: 'insert-text',
    insertText:
      'Review all changes in this worktree. Focus on correctness, regressions, edge cases, and missing tests.',
    section: 'Prompts',
  },
  {
    id: 'prompt:test-plan',
    name: 'Write a test plan',
    label: 'Write a test plan',
    description: 'Create a focused validation plan for this change.',
    behavior: 'insert-text',
    insertText:
      'Create a focused test plan for this change.\n\nInclude unit tests, integration coverage, and any manual verification steps.',
    section: 'Prompts',
  },
];

async function queryCommands(query: string): Promise<CommandItem[]> {
  await new Promise((r) => setTimeout(r, 60));
  const q = query.toLowerCase();
  return q
    ? MOCK_COMMANDS.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          (c.label ?? '').toLowerCase().includes(q) ||
          (c.description ?? '').toLowerCase().includes(q) ||
          (c.insertText ?? '').toLowerCase().includes(q)
      )
    : MOCK_COMMANDS;
}

// ── Mock permission modes (approveSettings) ───────────────────────────────────

const MOCK_PERMISSION_MODES: Record<string, ComposerPermissionModeOption> = {
  default: { name: 'Default', description: 'Prompt for each sensitive action.' },
  acceptEdits: {
    name: 'Accept edits',
    description: 'Auto-allow file edits, prompt for shell commands.',
  },
  plan: { name: 'Plan only', description: 'Agent proposes changes but never writes files.' },
  bypass: { name: 'Bypass all', description: 'Auto-approve everything — use with caution.' },
};

// ── Mock permission requests ──────────────────────────────────────────────────

const MOCK_PERMISSION_REQUESTS: ComposerPermissionRequest[] = [
  {
    requestId: 'req-1',
    title: 'Read a File',
    options: [
      { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
      { optionId: 'allow-always', name: 'Allow always', kind: 'allow_always' },
      { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
    ],
  },
  {
    requestId: 'req-2',
    title: 'Execute a Shell Command',
    options: [
      { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
      { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
    ],
  },
];

const MOCK_PERMISSION_OVERFLOW_REQUESTS: ComposerPermissionRequest[] = [
  {
    requestId: 'overflow-shell-command',
    title:
      'Execute a Shell Command: pnpm --filter @emdash/emdash-desktop run test:migrations -- --reporter=verbose --runInBand --updateSnapshot=false',
    options: [
      {
        optionId: 'allow-once-long',
        name: 'Allow once for this exact command invocation',
        kind: 'allow_once',
      },
      {
        optionId: 'allow-session-long',
        name: 'Allow matching pnpm migration validation commands for this session',
        kind: 'allow_always',
      },
      {
        optionId: 'reject-with-explanation-long',
        name: 'Reject and ask the agent to explain why this command is necessary first',
        kind: 'reject_once',
      },
    ],
  },
  {
    requestId: 'overflow-deep-path',
    title:
      'Edit /Users/davidkonopka/Documents/repos/emdash/apps/emdash-desktop/src/core/features/conversations/browser/acp/components/extremely-long-component-name-for-overflow-testing.tsx',
    options: [
      { optionId: 'allow-edit-once', name: 'Allow this edit once', kind: 'allow_once' },
      {
        optionId: 'allow-worktree-edits',
        name: 'Allow edits under this worktree path',
        kind: 'allow_always',
      },
      { optionId: 'reject-edit', name: 'Reject', kind: 'reject_once' },
    ],
  },
  {
    requestId: 'overflow-many-options',
    title: 'Run tool call with many available permission outcomes',
    options: [
      { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
      { optionId: 'allow-session', name: 'Allow for this session', kind: 'allow_always' },
      { optionId: 'allow-workspace', name: 'Allow for this workspace', kind: 'allow_always' },
      { optionId: 'redact-and-allow', name: 'Redact sensitive args and allow', kind: 'allow_once' },
      { optionId: 'reject-once', name: 'Reject once', kind: 'reject_once' },
      {
        optionId: 'reject-session',
        name: 'Reject matching requests this session',
        kind: 'reject_always',
      },
    ],
  },
];

const MOCK_QUEUED_PROMPTS: ComposerQueuedPrompt[] = [
  {
    id: 'queued-1',
    text: 'Add tests for prompt queue draining after a turn finishes.',
  },
  {
    id: 'queued-2',
    text: 'Refactor the queued prompt row actions into a reusable toolbar.',
  },
  {
    id: 'queued-3',
    text: 'Summarize the implementation tradeoffs before editing files.',
  },
];

const MOCK_CONTEXT_USAGE: ContextUsage = {
  used: 100_000,
  size: 200_000,
  cost: { amount: 0.42, currency: 'USD' },
};

const MOCK_HIGH_CONTEXT_USAGE: ContextUsage = {
  used: 185_000,
  size: 200_000,
  cost: { amount: 1.36, currency: 'USD' },
};

const MOCK_MCP_SERVERS: ComposerMcpServer[] = [
  { name: 'filesystem', transport: 'stdio' },
  { name: 'docs', transport: 'http' },
  { name: 'linear', transport: 'sse' },
];

interface PlaygroundArgs {
  disabled: boolean;
  isWorking: boolean;
  canSubmit: boolean;
  showAgentSelector: boolean;
  agentLocked: boolean;
  showModelSelector: boolean;
  showAttachButton: boolean;
  showNotice: boolean;
  noticeVariant: ComposerNoticeVariant;
  noticeTitle: string;
  noticeMessage: string;
  showPermissionModeSelector: boolean;
  showPermissionRequest: boolean;
  showQueuedPrompts: boolean;
}

function ComposerPlayground(args: PlaygroundArgs) {
  const {
    disabled,
    isWorking,
    canSubmit,
    showAgentSelector,
    agentLocked,
    showModelSelector,
    showAttachButton,
    showNotice,
    noticeVariant,
    noticeTitle,
    noticeMessage,
    showPermissionModeSelector,
    showPermissionRequest,
    showQueuedPrompts,
  } = args;

  const [selectedAgent, setSelectedAgent] = useState('claude');
  const [selectedModel, setSelectedModel] = useState('claude-sonnet-4-5');
  const [dismissed, setDismissed] = useState(false);
  const [selectedPermissionMode, setSelectedPermissionMode] = useState('default');
  const [permissionQueue, setPermissionQueue] = useState<ComposerPermissionRequest[]>([]);
  const [queuedPrompts, setQueuedPrompts] = useState<ComposerQueuedPrompt[]>([]);

  useEffect(() => {
    if (showNotice) setDismissed(false);
  }, [showNotice]);

  useEffect(() => {
    setPermissionQueue(showPermissionRequest ? MOCK_PERMISSION_REQUESTS : []);
  }, [showPermissionRequest]);

  useEffect(() => {
    setQueuedPrompts(showQueuedPrompts ? MOCK_QUEUED_PROMPTS : []);
  }, [showQueuedPrompts]);

  const noticeVisible = showNotice && !dismissed;
  const notice: ComposerNotice | null = noticeVisible
    ? {
        variant: noticeVariant,
        title: noticeTitle || undefined,
        message: noticeMessage,
        onDismiss: () => setDismissed(true),
      }
    : null;

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <Box marginBottom="3" display="flex" alignItems="center" gap="3">
        <Button
          size="xs"
          variant="ghost"
          tone="destructive"
          disabled={!noticeVisible}
          onClick={() => setDismissed(true)}
        >
          Dismiss
        </Button>
        <span className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))}>
          Toggle <code>showNotice</code> in Controls to watch the band transition in and out.
        </span>
      </Box>

      <ChatComposer
        disabled={disabled}
        isWorking={isWorking}
        canSubmit={canSubmit}
        agentOptions={showAgentSelector ? MOCK_AGENTS : null}
        selectedAgent={selectedAgent}
        onAgentChange={setSelectedAgent}
        agentLocked={agentLocked}
        modelOptions={showModelSelector ? MOCK_MODELS : null}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onSubmit={() => {}}
        onStop={() => {}}
        onAttach={showAttachButton ? () => {} : undefined}
        notice={notice}
        mentionProvider={mockMentionProvider}
        queryCommands={queryCommands}
        onCommand={(item) => console.log('command:', item.id)}
        permissionModeOptions={showPermissionModeSelector ? MOCK_PERMISSION_MODES : null}
        selectedPermissionMode={selectedPermissionMode}
        onPermissionModeChange={setSelectedPermissionMode}
        permissionRequest={permissionQueue[0] ?? null}
        permissionQueueCount={permissionQueue.length}
        onResolvePermission={() => setPermissionQueue((q) => q.slice(1))}
        queuedPrompts={queuedPrompts}
        onEditQueuedPrompt={(id, text) =>
          setQueuedPrompts((prompts) =>
            prompts.map((prompt) => (prompt.id === id ? { ...prompt, text } : prompt))
          )
        }
        onDeleteQueuedPrompt={(id) =>
          setQueuedPrompts((prompts) => prompts.filter((prompt) => prompt.id !== id))
        }
        onReorderQueuedPrompts={(ids) =>
          setQueuedPrompts((prompts) =>
            ids.flatMap((id) => {
              const prompt = prompts.find((item) => item.id === id);
              return prompt ? [prompt] : [];
            })
          )
        }
        onSendQueuedPromptNow={(id) => {
          console.log('send queued prompt now:', id);
          setQueuedPrompts((prompts) => prompts.filter((prompt) => prompt.id !== id));
        }}
      />
    </Box>
  );
}

const meta: Meta<PlaygroundArgs> = {
  title: 'Components/ChatComposer',
  parameters: { layout: 'centered' },
  render: (args) => <ComposerPlayground {...args} />,
  argTypes: {
    disabled: {
      control: 'boolean',
      description: 'Session closed — blocks the editor and controls.',
    },
    isWorking: { control: 'boolean', description: 'Agent is responding — shows the Stop button.' },
    canSubmit: {
      control: 'boolean',
      description: 'Session ready — when false, Send/Enter is blocked but typing is allowed.',
    },
    showAgentSelector: {
      control: 'boolean',
      description: 'Render the agent selector in the toolbar.',
    },
    agentLocked: {
      control: 'boolean',
      description: 'When true (prompt has been sent), the agent button is disabled.',
    },
    showModelSelector: {
      control: 'boolean',
      description: 'Render the model selector in the toolbar.',
    },
    showAttachButton: {
      control: 'boolean',
      description: 'Render the attachment (paperclip) button.',
    },
    showNotice: {
      control: 'boolean',
      description: 'Show the session-state notice band above the input.',
    },
    noticeVariant: {
      control: 'inline-radio',
      options: ['error', 'warning', 'info'],
      description: 'Notice color/severity.',
    },
    noticeTitle: { control: 'text', description: 'Optional notice heading.' },
    noticeMessage: { control: 'text', description: 'Notice body copy.' },
    showPermissionModeSelector: {
      control: 'boolean',
      description: 'Render the approval-policy (Permissions…) selector in the toolbar.',
    },
    showPermissionRequest: {
      control: 'boolean',
      description:
        'Seed a queue of mock permission requests. Resolve each with the SplitButton to advance to the next.',
    },
    showQueuedPrompts: {
      control: 'boolean',
      description: 'Seed a queue of mock prompts. Edit, delete, reorder, or send one now.',
    },
  },
  args: {
    disabled: false,
    isWorking: false,
    canSubmit: true,
    showAgentSelector: true,
    agentLocked: false,
    showModelSelector: true,
    showAttachButton: true,
    showNotice: false,
    noticeVariant: 'error',
    noticeTitle: 'Turn limit reached',
    noticeMessage:
      'The agent hit the maximum number of turn requests. Send a new message to continue.',
    showPermissionModeSelector: true,
    showPermissionRequest: false,
    showQueuedPrompts: false,
  },
};

export default meta;

type Story = StoryObj<PlaygroundArgs>;

/** Full controls playground — flip any arg in the Controls panel. */
export const Playground: Story = {};

export const WithMcpServers: Story = {
  render: () => (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <ChatComposer
        canSubmit
        modelOptions={MOCK_MODELS}
        selectedModel="claude-sonnet-4-5"
        permissionModeOptions={MOCK_PERMISSION_MODES}
        selectedPermissionMode="default"
        mcpServers={MOCK_MCP_SERVERS}
        mentionProvider={mockMentionProvider}
        queryCommands={queryCommands}
        onSubmit={() => {}}
      />
    </Box>
  ),
};

function QueuedPromptsDemo() {
  const [queuedPrompts, setQueuedPrompts] = useState<ComposerQueuedPrompt[]>(MOCK_QUEUED_PROMPTS);

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <ChatComposer
        isWorking
        canSubmit
        queuedPrompts={queuedPrompts}
        onEditQueuedPrompt={(id, text) =>
          setQueuedPrompts((prompts) =>
            prompts.map((prompt) => (prompt.id === id ? { ...prompt, text } : prompt))
          )
        }
        onDeleteQueuedPrompt={(id) =>
          setQueuedPrompts((prompts) => prompts.filter((prompt) => prompt.id !== id))
        }
        onReorderQueuedPrompts={(ids) =>
          setQueuedPrompts((prompts) =>
            ids.flatMap((id) => {
              const prompt = prompts.find((item) => item.id === id);
              return prompt ? [prompt] : [];
            })
          )
        }
        onSendQueuedPromptNow={(id) => {
          console.log('send queued prompt now:', id);
          setQueuedPrompts((prompts) => prompts.filter((prompt) => prompt.id !== id));
        }}
        onSubmitWhileWorking={(text) => {
          setQueuedPrompts((prompts) => [...prompts, { id: crypto.randomUUID(), text }]);
        }}
        onSubmit={() => {}}
        onStop={() => {}}
      />
    </Box>
  );
}

export const WithQueuedPrompts: Story = {
  render: () => <QueuedPromptsDemo />,
};

function QueuedPromptsWithPermissionRequestsDemo() {
  const [permissionQueue, setPermissionQueue] =
    useState<ComposerPermissionRequest[]>(MOCK_PERMISSION_REQUESTS);
  const [queuedPrompts, setQueuedPrompts] = useState<ComposerQueuedPrompt[]>(MOCK_QUEUED_PROMPTS);

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <ChatComposer
        isWorking
        canSubmit
        permissionRequest={permissionQueue[0] ?? null}
        permissionQueueCount={permissionQueue.length}
        onResolvePermission={() => setPermissionQueue((queue) => queue.slice(1))}
        queuedPrompts={queuedPrompts}
        onEditQueuedPrompt={(id, text) =>
          setQueuedPrompts((prompts) =>
            prompts.map((prompt) => (prompt.id === id ? { ...prompt, text } : prompt))
          )
        }
        onDeleteQueuedPrompt={(id) =>
          setQueuedPrompts((prompts) => prompts.filter((prompt) => prompt.id !== id))
        }
        onReorderQueuedPrompts={(ids) =>
          setQueuedPrompts((prompts) =>
            ids.flatMap((id) => {
              const prompt = prompts.find((item) => item.id === id);
              return prompt ? [prompt] : [];
            })
          )
        }
        onSendQueuedPromptNow={(id) => {
          console.log('send queued prompt now:', id);
          setQueuedPrompts((prompts) => prompts.filter((prompt) => prompt.id !== id));
        }}
        onSubmitWhileWorking={(text) => {
          setQueuedPrompts((prompts) => [...prompts, { id: crypto.randomUUID(), text }]);
        }}
        onSubmit={() => {}}
        onStop={() => {}}
      />
    </Box>
  );
}

export const WithQueuedPromptsAndPermissionRequests: Story = {
  render: () => <QueuedPromptsWithPermissionRequestsDemo />,
};

function PermissionBandOverflowStatesDemo() {
  const [lastAction, setLastAction] = useState<string | null>(null);

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <div style={{ display: 'grid', gap: '1rem' }}>
        {[
          {
            label: 'Narrow shell command',
            width: 320,
            widthLabel: '320px',
            request: MOCK_PERMISSION_OVERFLOW_REQUESTS[0],
          },
          {
            label: 'Medium deep path',
            width: 480,
            widthLabel: '480px',
            request: MOCK_PERMISSION_OVERFLOW_REQUESTS[1],
          },
          {
            label: 'Full width many options',
            width: '100%',
            widthLabel: '100%',
            request: MOCK_PERMISSION_OVERFLOW_REQUESTS[2],
          },
        ].map(({ label, width, widthLabel, request }, index) => (
          <div key={request.requestId} style={{ display: 'grid', gap: '0.375rem' }}>
            <div className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))} style={{ width }}>
              {label} · {widthLabel}
            </div>
            <div style={{ width, maxWidth: '100%' }}>
              <PermissionBand
                request={request}
                queueCount={index === 0 ? 12 : index + 1}
                onResolve={(optionId) => {
                  console.log('permission overflow action:', request.requestId, optionId);
                  setLastAction(`${request.requestId}: ${optionId}`);
                }}
              />
            </div>
          </div>
        ))}

        <div className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))}>
          Last action: {lastAction ?? 'none'}
        </div>
      </div>
    </Box>
  );
}

export const PermissionBandOverflowStates: Story = {
  render: () => <PermissionBandOverflowStatesDemo />,
};

function ContextUsageDemo({ usage }: { usage: ContextUsage }) {
  const [selectedModel, setSelectedModel] = useState('claude-sonnet-4-5');

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <ChatComposer
        modelOptions={MOCK_MODELS}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        contextUsage={usage}
        onSubmit={() => {}}
      />
    </Box>
  );
}

export const WithContextUsage: Story = {
  render: () => <ContextUsageDemo usage={MOCK_CONTEXT_USAGE} />,
};

export const WithHighContextUsage: Story = {
  render: () => <ContextUsageDemo usage={MOCK_HIGH_CONTEXT_USAGE} />,
};

// ── Effort selector story ─────────────────────────────────────────────────────

const MOCK_EFFORT_OPTIONS: Record<string, ComposerEffortOption> = {
  low: { name: 'Low', description: 'Faster, lighter reasoning.' },
  medium: { name: 'Medium', description: 'Balanced speed and depth.' },
  high: { name: 'High', description: 'Deepest reasoning, slower.' },
};

/**
 * WithEffortSelector — demonstrates the effort/thought-level submenu rendered
 * in the model popover footer. Click the model name in the toolbar, then hover
 * over the "Effort" row at the bottom to open the flyout and select a level.
 * The row is hidden entirely when `effortOptions` is null.
 */
function EffortSelectorDemo() {
  const [selectedModel, setSelectedModel] = useState('claude-sonnet-4-5');
  const [selectedEffort, setSelectedEffort] = useState<string | undefined>('medium');

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <ChatComposer
        modelOptions={MOCK_MODELS}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        effortOptions={MOCK_EFFORT_OPTIONS}
        selectedEffort={selectedEffort}
        onEffortChange={setSelectedEffort}
        onSubmit={() => {}}
      />
    </Box>
  );
}

export const WithEffortSelector: Story = {
  render: () => <EffortSelectorDemo />,
};

/**
 * WithoutEffortSelector — baseline confirming the effort row is absent when
 * `effortOptions` is null (agent doesn't advertise a thought_level option).
 */
function WithoutEffortSelectorDemo() {
  const [selectedModel, setSelectedModel] = useState('claude-sonnet-4-5');

  return (
    <Box className={cx(s.mxAuto, s.maxW2xl)} width="full">
      <ChatComposer
        modelOptions={MOCK_MODELS}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        effortOptions={null}
        onSubmit={() => {}}
      />
    </Box>
  );
}

export const WithoutEffortSelector: Story = {
  render: () => <WithoutEffortSelectorDemo />,
};

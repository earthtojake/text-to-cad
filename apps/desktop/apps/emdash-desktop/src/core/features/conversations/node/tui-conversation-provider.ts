import path from 'node:path';
import type { GitCredentialsSessionSpec } from '@emdash/core/primitives/git-credentials/api';
import type { HostRef } from '@emdash/core/primitives/host/api';
import type { TuiAgentStartInput } from '@emdash/core/runtimes/tui-agents/api';
import { makeTmuxSessionName } from '@emdash/core/services/pty/api';
import { and, eq } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type {
  ConversationProvider,
  EnsureConversationSessionRequest,
  EnsureConversationSessionResult,
} from '@core/features/conversations/api/node/types';
import {
  spillLargePrompt,
  type SpillLargePromptDeps,
  type SpillLargePromptResult,
} from '@core/features/conversations/node/spill-large-prompt';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';
import type { Conversation } from '@core/primitives/conversations/api';
import { makePtySessionId } from '@core/primitives/pty/api';
import type { AppDb } from '@core/services/app-db/node/db';
import type { TuiAgentsRuntimeClient } from '@core/services/runtime-broker/api/clients';
import {
  fileKey,
  fsErrorMessage,
  type FilesClientScope,
} from '@core/services/runtime-broker/node/files';

const DEFAULT_COLS = 80;
const DEFAULT_ROWS = 24;
const PROVIDER_SESSION_ID_REQUIRED_FOR_RESUME = new Set([
  'amp',
  'codex',
  'commandcode',
  'droid',
  'goose',
  'oh-my-pi',
  'pi',
]);

export type TuiConversationProviderOptions = {
  host: HostRef;
  files: FilesClientScope;
  tuiAgents: TuiAgentsRuntimeClient;
  projectId: string;
  taskId: string;
  taskPath: string;
  tmux?: boolean;
  shellSetup?: string;
  taskEnvVars?: Record<string, string>;
};

export type TuiConversationProviderDependencies = {
  db: AppDb;
  getProviderConfig(providerId: string): Promise<ProviderCustomConfig | undefined>;
  getTaskSettings(): Promise<{ autoTrustWorktrees: boolean }>;
  getTerminalColorEnv(): Promise<Record<string, string>>;
  /**
   * Per-session git credential behavior from the project's "agent git
   * credentials" setting (spec: github-git-settings §4); constructed into the
   * session env by the tui-agents runtime through the blessed builder.
   */
  resolveSessionGitCredentials(params: {
    projectId: string;
    host: HostRef;
  }): Promise<GitCredentialsSessionSpec | undefined>;
};

function parseExtraArgs(value: string | undefined): string[] {
  if (!value?.trim()) return [];
  return value.trim().split(/\s+/);
}

export class TuiConversationProvider implements ConversationProvider {
  private readonly projectId: string;
  private readonly taskId: string;
  private readonly taskPath: string;
  private readonly host: HostRef;
  private readonly files: FilesClientScope;
  private readonly tuiAgents: TuiAgentsRuntimeClient;
  private readonly tmux: boolean;
  private readonly shellSetup?: string;
  private readonly taskEnvVars: Record<string, string>;
  private readonly spills = new Map<string, SpillLargePromptResult>();

  constructor(
    options: TuiConversationProviderOptions,
    private readonly dependencies: TuiConversationProviderDependencies
  ) {
    this.projectId = options.projectId;
    this.taskId = options.taskId;
    this.taskPath = options.taskPath;
    this.host = options.host;
    this.files = options.files;
    this.tuiAgents = options.tuiAgents;
    this.tmux = options.tmux ?? false;
    this.shellSetup = options.shellSetup;
    this.taskEnvVars = options.taskEnvVars ?? {};
  }

  async ensureSession({
    conversation,
    mode,
    initialSize = { cols: DEFAULT_COLS, rows: DEFAULT_ROWS },
    initialPrompt,
  }: EnsureConversationSessionRequest): Promise<EnsureConversationSessionResult> {
    const input = await this.buildStartInput(conversation, initialSize, mode, initialPrompt);
    const agentSession = resolveAgentSession(conversation, mode);
    const result = agentSession.isResuming
      ? await this.tuiAgents.resume(input)
      : await this.tuiAgents.start(input);
    if (!result.success) {
      throw new Error(`TUI session failed to start: ${JSON.stringify(result.error)}`);
    }
    return { outcome: result.data.outcome };
  }

  async detachSession(_conversationId: string): Promise<void> {
    // Output subscriptions are passive; explicit control and idle cleanup own PTY lifetime.
  }

  async stopSession(conversationId: string): Promise<void> {
    await this.tuiAgents.stop({ conversationId });
    await this.cleanupSpill(conversationId);
  }

  async deleteSession(conversationId: string): Promise<void> {
    await this.tuiAgents.delete({ conversationId });
    await this.cleanupSpill(conversationId);
  }

  async destroyAll(): Promise<void> {
    const rows = await this.dependencies.db
      .select({ id: conversations.id })
      .from(conversations)
      .where(and(eq(conversations.taskId, this.taskId), eq(conversations.type, 'pty')));
    await Promise.all(rows.map((row) => this.stopSession(row.id)));
  }

  async detachAll(): Promise<void> {
    // Runtime leases are held by renderer output bindings; no provider-owned PTY to detach.
  }

  private async buildStartInput(
    conversation: Conversation,
    initialSize: { cols: number; rows: number },
    mode: 'start' | 'resume',
    initialPrompt: string | undefined
  ): Promise<TuiAgentStartInput> {
    const providerConfig = await this.dependencies.getProviderConfig(conversation.providerId);
    const trustWorkspace =
      conversation.autoApprove === true ||
      (await this.dependencies.getTaskSettings()).autoTrustWorktrees;
    const agentSession = resolveAgentSession(conversation, mode);
    const effectiveInitialPrompt = await this.effectiveInitialPrompt(
      conversation.id,
      !agentSession.isResuming && mode === 'start' ? initialPrompt : undefined
    );
    const colorEnv = await this.dependencies.getTerminalColorEnv();
    const providerVars = {
      ...(providerConfig?.env ?? {}),
      ...colorEnv,
      ...this.taskEnvVars,
    };
    const sessionId = makePtySessionId(this.projectId, this.taskId, conversation.id);
    const gitCredentials = await this.dependencies.resolveSessionGitCredentials({
      projectId: this.projectId,
      host: this.host,
    });

    return {
      conversationId: conversation.id,
      providerId: conversation.providerId,
      cwd: this.taskPath,
      sessionId: agentSession.isResuming ? agentSession.sessionId : null,
      // Fresh spawns declare the emdash-chosen resume handle (resolveAgentSession falls
      // back to the conversation id), so the index learns it at spawn (spec §3.1).
      chosenSessionId: agentSession.isResuming ? null : agentSession.sessionId,
      model: conversation.model ?? null,
      initialPrompt: effectiveInitialPrompt,
      autoApprove: conversation.autoApprove ?? false,
      trustWorkspace,
      extraArgs: parseExtraArgs(providerConfig?.extraArgs),
      providerVars,
      gitCredentials,
      cols: initialSize.cols,
      rows: initialSize.rows,
      shellSetup: this.shellSetup,
      tmuxSessionName: this.tmux ? makeTmuxSessionName(sessionId) : undefined,
    };
  }

  private async effectiveInitialPrompt(
    conversationId: string,
    initialPrompt: string | undefined
  ): Promise<string | undefined> {
    if (!initialPrompt) return undefined;
    await this.cleanupSpill(conversationId);
    const spill = await spillLargePrompt(
      initialPrompt,
      createWorkspacePromptSpillDeps(this.files, this.taskPath, conversationId)
    );
    this.spills.set(conversationId, spill);
    return spill.prompt;
  }

  private async cleanupSpill(conversationId: string): Promise<void> {
    const spill = this.spills.get(conversationId);
    if (!spill) return;
    this.spills.delete(conversationId);
    await spill.cleanup();
  }
}

export function createWorkspacePromptSpillDeps(
  files: FilesClientScope,
  taskPath: string,
  conversationId: string
): SpillLargePromptDeps {
  const emdashDir = path.join(taskPath, '.emdash');
  const tmpDir = path.join(emdashDir, 'tmp');
  const promptDir = path.join(tmpDir, `prompt-${conversationId}`);

  return {
    createTempDir: async () => {
      for (const directory of [emdashDir, tmpDir, promptDir]) {
        const result = await files.client.fs.createDirectory(fileKey(files, directory));
        if (!result.success && result.error.type !== 'already-exists') {
          throw new Error(fsErrorMessage(result.error));
        }
      }
      return promptDir;
    },
    writeContextFile: async (filePath, contents) => {
      const result = await files.client.fs.writeFile({
        ...fileKey(files, filePath),
        content: contents,
        precondition: { kind: 'overwrite' },
      });
      if (!result.success) throw new Error(fsErrorMessage(result.error));
    },
    removeTempDir: async (directory) => {
      const result = await files.client.fs.delete({
        ...fileKey(files, directory),
        recursive: true,
      });
      if (!result.success && result.error.type !== 'not-found') {
        throw new Error(fsErrorMessage(result.error));
      }
    },
  };
}

function resolveAgentSession(
  conversation: Conversation,
  mode: 'start' | 'resume'
): { sessionId: string; isResuming: boolean } {
  const isResuming = mode === 'resume';
  if (PROVIDER_SESSION_ID_REQUIRED_FOR_RESUME.has(conversation.providerId) && isResuming) {
    const nativeSessionId = conversation.sessionId;
    if (nativeSessionId && nativeSessionId !== conversation.id) {
      return { sessionId: nativeSessionId, isResuming: true };
    }
    return { sessionId: conversation.id, isResuming: false };
  }

  return { sessionId: conversation.id, isResuming };
}

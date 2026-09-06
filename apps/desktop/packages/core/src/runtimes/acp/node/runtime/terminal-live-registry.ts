import { LiveLogSource } from '@emdash/wire/live';
import type { AgentTerminalHooks } from '#runtimes/acp/node/agent-ports/terminal-manager';

type TerminalRecord = {
  conversationId: string;
  truncated: boolean;
  log: LiveLogSource;
};

/**
 * Mirrors terminal hook callbacks into live primitives.
 *
 * Terminal metadata/status is exposed as one LiveModel per conversation
 * (published by the session manager from AgentTerminalManager snapshots).
 * Terminal output text flows exclusively through one capped LiveLogSource per
 * terminal — the registry retains no output text of its own, so its state
 * stays constant-size no matter how much a terminal streams.
 *
 * Conversation-level republish fires only on lifecycle transitions (create,
 * exit, release, and the first truncation) — never per output chunk.
 */
export class TerminalLiveRegistry {
  private readonly byTerminal = new Map<string, TerminalRecord>();

  constructor(private readonly onConversationChanged?: (conversationId: string) => void) {}

  readonly hooks: AgentTerminalHooks = {
    onTerminalCreated: ({ conversationId, terminalId }) => {
      this.byTerminal.set(terminalId, {
        conversationId,
        truncated: false,
        log: new LiveLogSource(),
      });
      this.onConversationChanged?.(conversationId);
    },
    onTerminalOutput: ({ conversationId, terminalId, chunk, truncated }) => {
      const record = this.byTerminal.get(terminalId);
      if (!record) return;
      record.log.append(chunk);
      if (truncated && !record.truncated) {
        record.truncated = true;
        this.onConversationChanged?.(conversationId);
      }
    },
    onTerminalExit: ({ conversationId }) => {
      this.onConversationChanged?.(conversationId);
    },
    onTerminalReleased: ({ conversationId, terminalId }) => {
      this.byTerminal.delete(terminalId);
      this.onConversationChanged?.(conversationId);
    },
  };

  getTerminalLog(terminalId: string): LiveLogSource | null {
    return this.byTerminal.get(terminalId)?.log ?? null;
  }
}

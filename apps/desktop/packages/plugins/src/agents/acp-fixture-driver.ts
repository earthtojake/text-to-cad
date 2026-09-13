/**
 * Shared helper for ACP transcript fixture tests.
 *
 * Drives an `AcpTranscriptParser` instance through a recorded fixture event
 * log, synthesizing user_message_chunk updates from `prompt` entries and
 * calling `endTurn()` on `prompt_result` entries.
 *
 * Intentionally has no Vitest imports — this is a plain utility module, not a
 * test file. Both `claude` and `codex` fixture tests import from here.
 */
import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { AcpTranscriptParser, type TranscriptTurnOutcome } from '@emdash/core/runtimes/acp/api';

// ── Narrow fixture types (mirrors recorder.ts shapes for the used fields) ────

interface RecordedPrompt {
  kind: 'prompt';
  sessionId: string;
  content: Array<{ type: string; text?: string }>;
}
interface RecordedSessionUpdate {
  kind: 'session_update';
  sessionId: string;
  update: unknown;
}
interface RecordedPromptResult {
  kind: 'prompt_result';
  sessionId: string;
  stopReason: string | null | undefined;
}
type AnyRecordedEvent =
  | RecordedPrompt
  | RecordedSessionUpdate
  | RecordedPromptResult
  | { kind: string };

export interface RecordedEntry {
  seq: number;
  ts: number;
  event: AnyRecordedEvent;
}

/**
 * Feed all entries from a fixture log into a fresh `AcpTranscriptParser` and
 * return the parser instance so callers can snapshot `.snapshot` or make
 * additional assertions.
 */
export function driveParser(events: RecordedEntry[], conversationId: string): AcpTranscriptParser {
  const parser = new AcpTranscriptParser({ conversationId });

  for (const entry of events) {
    const kind = (entry.event as { kind: string }).kind;

    switch (kind) {
      case 'prompt': {
        const ev = entry.event as RecordedPrompt;
        // Synthesize a user_message_chunk for each text block in the prompt.
        for (const block of ev.content) {
          if (block.type === 'text' && block.text) {
            parser.push(
              {
                sessionUpdate: 'user_message_chunk',
                sessionId: ev.sessionId,
                messageId: undefined,
                content: { type: 'text', text: block.text },
              } as unknown as SessionUpdate,
              entry.ts
            );
          }
        }
        break;
      }
      case 'session_update': {
        const ev = entry.event as RecordedSessionUpdate;
        parser.push(ev.update as SessionUpdate, entry.ts);
        break;
      }
      case 'prompt_result': {
        const ev = entry.event as RecordedPromptResult;
        parser.settleTurn(outcomeFromRecordedStopReason(ev.stopReason), entry.ts);
        break;
      }
      default:
        break;
    }
  }

  return parser;
}

function outcomeFromRecordedStopReason(
  stopReason: string | null | undefined
): TranscriptTurnOutcome {
  if (stopReason === 'cancelled') return { kind: 'cancelled', reason: 'cancelled' };
  if (
    stopReason === 'end_turn' ||
    stopReason === 'max_tokens' ||
    stopReason === 'max_turn_requests' ||
    stopReason === 'refusal'
  ) {
    return { kind: 'done', reason: stopReason };
  }
  return { kind: 'done' };
}

import { readFileSync } from 'node:fs';
import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { EnrichHook } from '@emdash/core/runtimes/acp/api';
import { AcpTranscriptParser } from '@emdash/core/runtimes/acp/api';

export interface RecordedPrompt {
  kind: 'prompt';
  sessionId: string;
  content: Array<{ type: string; text?: string }>;
}

export interface RecordedSessionUpdate {
  kind: 'session_update';
  sessionId: string;
  update: unknown;
}

export interface RecordedPromptResult {
  kind: 'prompt_result';
  sessionId: string;
  stopReason: string | null | undefined;
}

export interface RecordedConfigOptionSet {
  kind: 'config_option_set';
  sessionId: string;
  responseConfigOptions: unknown;
}

export interface RecordedModeSet {
  kind: 'mode_set';
  sessionId: string;
  modeId: string;
}

export type RecordedEvent =
  | RecordedPrompt
  | RecordedSessionUpdate
  | RecordedPromptResult
  | RecordedConfigOptionSet
  | RecordedModeSet;

export interface RecordedEntry {
  seq: number;
  ts: number;
  event: RecordedEvent | { kind: string };
}

export interface FixtureFile {
  meta: {
    sessionId: string;
    providerId: string;
    initialConfigOptions?: unknown;
  };
  events: RecordedEntry[];
}

export interface DriveParserOptions {
  enrich?: EnrichHook;
}

export function loadFixture(url: URL): FixtureFile {
  return JSON.parse(readFileSync(url, 'utf8')) as FixtureFile;
}

export function driveParser(
  fixture: FixtureFile,
  options: DriveParserOptions = {}
): AcpTranscriptParser {
  const { meta, events } = fixture;
  const parser = new AcpTranscriptParser({
    conversationId: meta.sessionId,
    ...(options.enrich ? { enrich: options.enrich } : {}),
  });

  if (Array.isArray(meta.initialConfigOptions)) {
    parser.push({
      sessionUpdate: 'config_option_update',
      sessionId: meta.sessionId,
      configOptions: meta.initialConfigOptions,
    } as unknown as SessionUpdate);
  }

  for (const entry of events) {
    const kind = (entry.event as { kind: string }).kind;

    switch (kind) {
      case 'prompt': {
        const ev = entry.event as RecordedPrompt;
        for (const block of ev.content) {
          if (block.type === 'text' && block.text) {
            parser.push({
              sessionUpdate: 'user_message_chunk',
              sessionId: ev.sessionId,
              messageId: undefined,
              content: { type: 'text', text: block.text },
            } as unknown as SessionUpdate);
          }
        }
        break;
      }
      case 'session_update': {
        const ev = entry.event as RecordedSessionUpdate;
        parser.push(ev.update as SessionUpdate);
        break;
      }
      case 'prompt_result':
        parser.endTurn();
        break;
      case 'config_option_set': {
        const ev = entry.event as RecordedConfigOptionSet;
        if (Array.isArray(ev.responseConfigOptions)) {
          parser.push({
            sessionUpdate: 'config_option_update',
            sessionId: ev.sessionId,
            configOptions: ev.responseConfigOptions,
          } as unknown as SessionUpdate);
        }
        break;
      }
      case 'mode_set': {
        const ev = entry.event as RecordedModeSet;
        parser.push({
          sessionUpdate: 'current_mode_update',
          sessionId: ev.sessionId,
          currentModeId: ev.modeId,
        } as unknown as SessionUpdate);
        break;
      }
      default:
        break;
    }
  }

  return parser;
}

import type { SessionUpdate } from '@agentclientprotocol/sdk';

export interface RawAcpLogMeta {
  conversationId: string;
  providerId: string;
  acpSessionId: string;
  createdAt: string;
}

export interface RawAcpLogExportMeta extends RawAcpLogMeta {
  generatedAt: string;
}

export interface RawAcpSessionUpdateEvent {
  kind: 'session_update';
  sessionId: string;
  update: SessionUpdate;
}

export interface RawAcpPromptEvent {
  kind: 'prompt';
  sessionId: string;
  content: unknown;
}

export interface RawAcpPromptResultEvent {
  kind: 'prompt_result';
  sessionId: string;
  stopReason: string | null | undefined;
}

export interface RawAcpPermissionRequestEvent {
  kind: 'permission_request';
  sessionId: string;
  request: unknown;
}

export interface RawAcpPermissionResolvedEvent {
  kind: 'permission_resolved';
  sessionId: string;
  requestId: string;
  optionId: string;
}

export type RawAcpEvent =
  | RawAcpSessionUpdateEvent
  | RawAcpPromptEvent
  | RawAcpPromptResultEvent
  | RawAcpPermissionRequestEvent
  | RawAcpPermissionResolvedEvent;

export interface RawAcpLogEntry {
  seq: number;
  ts: number;
  event: RawAcpEvent;
}

const DEFAULT_MAX_ENTRIES = 50_000;
// Retention is capped by bytes as well as entries so a chatty session (large tool
// results, big prompts) cannot grow the in-memory log without bound.
const DEFAULT_MAX_BYTES = 16 * 1024 * 1024;

export interface RawAcpLogOptions {
  maxEntries?: number;
  maxBytes?: number;
}

/**
 * Append-only, fixture-compatible log of raw ACP traffic observed by a session.
 * This records data at the runtime boundary before the reducer normalizes it.
 */
export class RawAcpLog {
  private seq = 0;
  private readonly entries: RawAcpLogEntry[] = [];
  private readonly entryBytes: number[] = [];
  private totalBytes = 0;
  private readonly maxEntries: number;
  private readonly maxBytes: number;

  constructor(
    private readonly meta: RawAcpLogMeta,
    options: RawAcpLogOptions = {}
  ) {
    this.maxEntries = options.maxEntries ?? DEFAULT_MAX_ENTRIES;
    this.maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
  }

  setAcpSessionId(acpSessionId: string): void {
    this.meta.acpSessionId = acpSessionId;
  }

  record(event: RawAcpEvent): void {
    let bytes: number;
    try {
      const json = JSON.stringify(event);
      bytes = json === undefined ? 0 : Buffer.byteLength(json, 'utf8');
    } catch {
      bytes = 0;
    }
    this.entries.push({ seq: this.seq++, ts: Date.now(), event });
    this.entryBytes.push(bytes);
    this.totalBytes += bytes;
    this.evict();
  }

  private evict(): void {
    while (
      this.entries.length > 1 &&
      (this.entries.length > this.maxEntries || this.totalBytes > this.maxBytes)
    ) {
      this.entries.shift();
      this.totalBytes -= this.entryBytes.shift() ?? 0;
    }
  }

  snapshot(): { meta: RawAcpLogExportMeta; events: RawAcpLogEntry[] } {
    return {
      meta: {
        ...this.meta,
        generatedAt: new Date().toISOString(),
      },
      events: structuredClone(this.entries),
    };
  }

  exportJson(): string {
    return JSON.stringify(this.snapshot(), null, 2);
  }
}

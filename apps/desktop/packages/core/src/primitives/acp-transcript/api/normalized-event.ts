import type {
  AvailableCommand,
  SessionConfigOption,
  SessionUpdate,
} from '@agentclientprotocol/sdk';

export type AttachmentRef = {
  id: string;
  name: string;
  mimeType: 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp';
};

export type SessionRateLimit = {
  status: 'allowed' | 'allowed_warning' | 'rejected';
  /** Epoch seconds when the limit resets, when the provider says. */
  resetsAt?: number;
  rateLimitType?: string;
  /** Fraction of the limit already used, when the provider says. */
  utilization?: number;
};

export type SessionUsage = {
  contextSize: number;
  contextUsed: number;
  cost: { amount: number; currency: string } | null;
  /** Provider account limits reported beside usage (Claude); absent for others. */
  rateLimit?: SessionRateLimit;
};

export type PlanEntryInput = {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  priority: 'high' | 'medium' | 'low';
};

export type NormalizedDiff = {
  path: string;
  oldText: string | null;
  newText: string;
};

export type NormalizedToolStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

/** An ACP `resource_link` content block: a file or URL the agent points the user at. */
export type NormalizedResourceLink = {
  uri: string;
  name: string;
  title?: string;
  description?: string;
  mimeType?: string;
  size?: number;
};

/** A file location an ACP tool call reports touching. */
export type NormalizedToolLocation = { path: string; line?: number };

export type NormalizedEvent =
  | {
      kind: 'message';
      role: 'user' | 'assistant';
      messageId: string | null;
      text: string;
      attachments?: AttachmentRef[];
      /** Resources the message links to; each becomes its own row after the text. */
      links?: NormalizedResourceLink[];
    }
  | {
      kind: 'thinking';
      messageId: string | null;
      text: string;
    }
  | {
      kind: 'tool_call';
      toolCallId: string;
      title: string;
      toolKind: string | null;
      status: NormalizedToolStatus | null;
      parentToolCallId: string | null;
      diffs: NormalizedDiff[];
      inputSummary?: string;
      outputText?: string;
      terminalId?: string;
      locations?: NormalizedToolLocation[];
      /** Runtime-owned image output references; never provider base64 payloads. */
      attachments?: AttachmentRef[];
    }
  | {
      kind: 'subagent';
      toolCallId: string;
      title: string;
      status: NormalizedToolStatus | null;
      parentToolCallId: string | null;
      inputSummary?: string;
      background?: boolean;
      agentId?: string;
      outputFile?: string;
      /** Text the agent reported back, when the provider surfaces it. */
      outputText?: string;
      attachments?: AttachmentRef[];
    }
  | {
      kind: 'subagent_update';
      toolCallId?: string;
      agentId?: string;
      status: NormalizedToolStatus;
      summary?: string;
      outputFile?: string;
    }
  | {
      kind: 'search';
      toolCallId: string;
      query: string;
      /** Where the provider searched. Omitted for older or provider-ambiguous events. */
      scope?: 'web' | 'workspace';
      status: NormalizedToolStatus | null;
      parentToolCallId: string | null;
      matchCount?: number;
      /** Result text the provider reported for the search, when it surfaces one. */
      outputText?: string;
      attachments?: AttachmentRef[];
    }
  | {
      kind: 'mcp_tool';
      toolCallId: string;
      server?: string;
      tool: string;
      status: NormalizedToolStatus | null;
      parentToolCallId: string | null;
      inputSummary?: string;
      attachments?: AttachmentRef[];
    }
  | {
      kind: 'web_fetch';
      toolCallId: string;
      url: string;
      title?: string;
      status: NormalizedToolStatus | null;
      parentToolCallId: string | null;
      /** Fetched text the provider reported, when it surfaces one. */
      outputText?: string;
      attachments?: AttachmentRef[];
    }
  | {
      kind: 'tool_update';
      toolCallId: string;
      title: string | null;
      toolKind: string | null;
      status: NormalizedToolStatus | null;
      parentToolCallId: string | null;
      diffs: NormalizedDiff[];
      outputText?: string;
      terminalId?: string;
      locations?: NormalizedToolLocation[];
      /** Latest provider progress line for a call that is still running. */
      progress?: string;
      /** Runtime-owned image output references; never provider base64 payloads. */
      attachments?: AttachmentRef[];
    }
  | {
      kind: 'plan';
      entries: PlanEntryInput[];
    }
  | {
      kind: 'config';
      options: ReadonlyArray<SessionConfigOption>;
    }
  | {
      kind: 'mode_selected';
      modeId: string;
    }
  | {
      kind: 'commands';
      commands: ReadonlyArray<AvailableCommand>;
    }
  | {
      kind: 'usage';
      usage: SessionUsage;
    }
  | {
      kind: 'title';
      title: string;
    }
  | { kind: 'ignored' };

export type EnrichHook = (event: NormalizedEvent, raw: SessionUpdate) => NormalizedEvent;

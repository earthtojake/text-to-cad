/**
 * Local stand-ins for the handful of types the vendored AI Elements borrow
 * from Vercel's `ai` package.
 *
 * Hardcore talks to agents over the Agent Client Protocol, not the AI SDK
 * (plan §4: "No AI SDK dependency"), and every `ai` import in the vendored
 * components was `import type` — nothing here ran at runtime. Declaring the
 * shapes locally keeps the components compiling and keeps a ~large model-
 * provider SDK out of the dependency tree.
 *
 * These are structural copies of the AI SDK's UI types, faithful to the
 * fields the components actually read. When re-vendoring an AI Element,
 * repoint its `from "ai"` import here (`./types`) and extend this file if the
 * new component needs a field that is missing.
 */

/** Lifecycle of a chat turn, as the composer's send/stop button reads it. */
export type ChatStatus = "submitted" | "streaming" | "ready" | "error";

/** A file attached to a message. */
export type FileUIPart = {
  type: "file";
  filename?: string;
  mediaType?: string;
  url?: string;
};

/** A document cited as a source. */
export type SourceDocumentUIPart = {
  type: "source-document";
  sourceId?: string;
  title?: string;
  filename?: string;
  mediaType?: string;
  url?: string;
};

/** A plain text run inside a message. */
export type TextUIPart = {
  type: "text";
  text: string;
  state?: "streaming" | "done";
};

/** A model's reasoning run inside a message. */
export type ReasoningUIPart = {
  type: "reasoning";
  text: string;
  state?: "streaming" | "done";
};

/** Every state a tool call passes through, in the order the UI labels them. */
export type ToolUIPartState =
  | "input-streaming"
  | "input-available"
  | "approval-requested"
  | "approval-responded"
  | "output-available"
  | "output-denied"
  | "output-error";

/** A call to a tool the agent declared up front. */
export type ToolUIPart = {
  type: `tool-${string}`;
  toolCallId?: string;
  state: ToolUIPartState;
  input?: unknown;
  output?: unknown;
  errorText?: string;
};

/** A call to a tool discovered at run time (MCP servers, for instance). */
export type DynamicToolUIPart = {
  type: "dynamic-tool";
  toolName: string;
  toolCallId?: string;
  state: ToolUIPartState;
  input?: unknown;
  output?: unknown;
  errorText?: string;
};

/** Anything that can appear in a message body. */
export type UIMessagePart =
  | TextUIPart
  | ReasoningUIPart
  | FileUIPart
  | SourceDocumentUIPart
  | ToolUIPart
  | DynamicToolUIPart;

/** One turn of a conversation. */
export type UIMessage = {
  id: string;
  role: "system" | "user" | "assistant";
  parts: UIMessagePart[];
  metadata?: unknown;
};

/** Token counts for a turn, as the Context meter reads them. */
export type LanguageModelUsage = {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  reasoningTokens?: number;
  cachedInputTokens?: number;
};

/** A tool definition, as the Agent card renders it. */
export type Tool = {
  description?: string;
  inputSchema?: unknown;
  jsonSchema?: unknown;
};

/** Generated image payload. */
export type Experimental_GeneratedImage = {
  base64: string;
  uint8Array?: Uint8Array;
  mediaType: string;
};

/** Synthesised speech payload. */
export type Experimental_SpeechResult = {
  audio: {
    base64: string;
    uint8Array?: Uint8Array;
    mediaType: string;
  };
};

/** Transcription payload, with the per-segment timings the UI seeks on. */
export type Experimental_TranscriptionResult = {
  text: string;
  segments: {
    text: string;
    startSecond: number;
    endSecond: number;
  }[];
  language?: string;
  durationInSeconds?: number;
};

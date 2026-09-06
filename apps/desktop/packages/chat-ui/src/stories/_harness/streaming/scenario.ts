/**
 * Streaming scenario builders — pure, Solid-free functions that produce
 * ScriptStep[] arrays for use with ScriptedChat.
 *
 * No Solid imports so this module can run in the Node Vitest project.
 *
 * All builders use `driveEvent(api, event)` internally, which calls
 * `api.activeTurn.set(applyTurnEvent(api.activeTurn.get(), event), 'generating')`.
 * Turn-lifecycle termination uses `api.activeTurn.commit(status)`.
 */

import type { TranscriptApi } from '@state/transcript';
import type { ChatItem, ChatRole, FileOp, FileOpKind, ToolStatus } from '@/model';
import type { ScriptStep } from '@/stories/_harness/chat-host';
import type { ActiveTurnEvent } from '@/stories/_harness/turn-reducer';
import { applyTurnEvent } from '@/stories/_harness/turn-reducer';

// ── driveEvent helper ─────────────────────────────────────────────────────────

/**
 * Apply one ActiveTurnEvent to a transcript's activeTurn via applyTurnEvent.
 *
 * Reads the current desired snapshot from `api.activeTurn.get()`, folds in the
 * event immutably, and pushes the result via `api.activeTurn.set`.  Used by all
 * scenario step functions so they work with both the raw transcript and any
 * wrapTranscript adapter (e.g. createStreamSmoother).
 */
function driveEvent(api: TranscriptApi, event: ActiveTurnEvent): void {
  const current = api.activeTurn.get();
  api.activeTurn.set(applyTurnEvent(current, event), 'generating');
}

// ── Chunk splitting ───────────────────────────────────────────────────────────

export type ChunkMode = 'word' | 'char' | 'line';

/**
 * Split `text` into chunks preserving all whitespace so concatenation always
 * equals the original string.
 *
 * - `word` (default): splits on whitespace boundaries, keeping whitespace as
 *   its own atoms; `size` groups that many atoms per chunk.
 * - `char`: one Unicode code point per atom; `size` groups that many chars.
 * - `line`: one line (including its trailing `\n`) per atom.
 */
export function chunkText(text: string, opts: { mode?: ChunkMode; size?: number } = {}): string[] {
  const { mode = 'word', size = 1 } = opts;

  let atoms: string[];
  if (mode === 'char') {
    atoms = Array.from(text);
  } else if (mode === 'line') {
    // Split keeping the trailing newline attached to the preceding line.
    atoms = text.split(/(?<=\n)/);
    // Remove trailing empty string that split() can leave.
    if (atoms.length > 0 && atoms[atoms.length - 1] === '') atoms.pop();
  } else {
    // word: alternate between non-whitespace runs and whitespace runs.
    atoms = text.split(/(\s+)/).filter((a) => a.length > 0);
  }

  if (atoms.length === 0) return text.length > 0 ? [text] : [];

  const chunks: string[] = [];
  for (let i = 0; i < atoms.length; i += size) {
    chunks.push(atoms.slice(i, i + size).join(''));
  }
  return chunks;
}

// ── Composition helpers ───────────────────────────────────────────────────────

/** Flatten multiple step arrays into one. */
export function scenario(...parts: ScriptStep[][]): ScriptStep[] {
  return parts.flat();
}

/** Create a seed step from a list of items. */
export function seedStep(items: ChatItem[]): ScriptStep {
  return { kind: 'seed', items };
}

// ── Scenario builders ─────────────────────────────────────────────────────────

/**
 * Produce steps that stream an assistant (or user) message word-by-word.
 *
 * A zero-length `message_chunk` is emitted first — synchronously, before any
 * wait — so the row is created immediately in the virtualizer. This matches
 * the behavior of working scripted stories where the row exists before any
 * async timers fire.
 */
export function streamMessage(opts: {
  id: string;
  role?: ChatRole;
  text: string;
  /** Delay between chunks in ms (default: 60). */
  chunkMs?: number;
  /** Chunking options (default: word, size 1). */
  chunk?: { mode?: ChunkMode; size?: number };
  /** Emit turn_done at the end (default: true). */
  finalize?: boolean;
}): ScriptStep[] {
  const { id, role = 'assistant', text, chunkMs = 60, chunk = {}, finalize = true } = opts;
  const chunks = chunkText(text, chunk);

  const steps: ScriptStep[] = [];

  // Create the row synchronously so it exists before any setTimeout fires.
  steps.push({
    kind: 'call',
    fn: (api: TranscriptApi) => driveEvent(api, { type: 'message_chunk', id, role, text: '' }),
  });

  for (const c of chunks) {
    steps.push({ kind: 'wait', ms: chunkMs });
    steps.push({
      kind: 'call',
      fn: (api: TranscriptApi) => driveEvent(api, { type: 'message_chunk', id, role, text: c }),
    });
  }

  if (finalize) {
    steps.push({ kind: 'wait', ms: chunkMs });
    steps.push({
      kind: 'call',
      fn: (api: TranscriptApi) => api.activeTurn.commit('done'),
    });
  }

  return steps;
}

/**
 * Produce steps that stream a thinking row, then mark it done.
 *
 * An empty `thinking_chunk` is emitted first (synchronously) to create the
 * row with `startedAt = Date.now()`. Subsequent chunks append text.
 */
export function streamThinking(opts: {
  id: string;
  text: string;
  /** Delay between chunks in ms (default: 60). */
  chunkMs?: number;
  /**
   * If provided, `thinking_done` is emitted with this exact duration.
   * Otherwise the duration is derived from `startedAt` at emit time.
   */
  durationMs?: number;
  /** Chunking options (default: word, size 2 — word+space pairs). */
  chunk?: { mode?: ChunkMode; size?: number };
}): ScriptStep[] {
  const { id, text, chunkMs = 60, durationMs, chunk = { mode: 'word', size: 2 } } = opts;
  const chunks = chunkText(text, chunk);

  const steps: ScriptStep[] = [];

  // Create the row synchronously; Date.now() runs at call time (dispatch time).
  steps.push({
    kind: 'call',
    fn: (api: TranscriptApi) =>
      driveEvent(api, { type: 'thinking_chunk', id, text: '', startedAt: Date.now() }),
  });

  for (const c of chunks) {
    steps.push({ kind: 'wait', ms: chunkMs });
    steps.push({
      kind: 'call',
      fn: (api: TranscriptApi) => driveEvent(api, { type: 'thinking_chunk', id, text: c }),
    });
  }

  steps.push({ kind: 'wait', ms: chunkMs });
  steps.push({
    kind: 'call',
    fn: (api: TranscriptApi) =>
      driveEvent(api, {
        type: 'thinking_done',
        id,
        ...(durationMs !== undefined ? { durationMs } : {}),
      }),
  });

  return steps;
}

/**
 * Produce steps that simulate a file-operation tool call: the first path
 * is revealed synchronously, then each subsequent path is added one at a
 * time with a configurable delay.
 *
 * Each `file_op_update` sends the *full* accumulated list so far (matching
 * ACP's "replaces locations collection" semantics). Ends with a
 * `file_op_update` that sets status to `finalStatus` (default: 'done').
 */
export function streamFileOp(opts: {
  id: string;
  op: FileOpKind;
  /** Paths to reveal progressively. At least one is required. */
  paths: string[];
  /** Delay between revealing each new path in ms (default: 300). */
  pathMs?: number;
  /** Final status dispatched after the last path (default: 'done'). */
  finalStatus?: ToolStatus;
  /** Optional id of the parent tool call for hierarchical rendering. */
  parentId?: string;
}): ScriptStep[] {
  const { id, op, paths, pathMs = 300, finalStatus = 'done', parentId } = opts;

  if (paths.length === 0) return [];

  const result: ScriptStep[] = [];

  // Create the row synchronously with the first path.
  const firstOps: FileOp[] = [{ path: paths[0] }];
  result.push({
    kind: 'call',
    fn: (api: TranscriptApi) =>
      driveEvent(api, {
        type: 'file_op_start',
        id,
        op,
        ops: firstOps,
        ...(parentId !== undefined ? { parentId } : {}),
      }),
  });

  // Reveal remaining paths one by one, each update includes all paths so far.
  for (let i = 1; i < paths.length; i++) {
    const accumulatedOps: FileOp[] = paths.slice(0, i + 1).map((path) => ({ path }));
    result.push({ kind: 'wait', ms: pathMs });
    result.push({
      kind: 'call',
      fn: (api: TranscriptApi) =>
        driveEvent(api, { type: 'file_op_update', id, ops: accumulatedOps }),
    });
  }

  // Finalize.
  result.push({ kind: 'wait', ms: pathMs });
  result.push({
    kind: 'call',
    fn: (api: TranscriptApi) =>
      driveEvent(api, { type: 'file_op_update', id, status: finalStatus }),
  });

  return result;
}

/**
 * Produce steps that simulate a diff preview streaming in:
 *
 *   1. `diff_start` with empty `newText` (synchronous) — the row appears as a
 *      header-only card with the file name shimmering (Stage A).
 *   2. After `headerMs`, content is revealed line-by-line via `diff_update`,
 *      each update sending the full accumulated text (Stage B — streaming body).
 *   3. A final `diff_update` flips status to `finalStatus`, dropping the shimmer
 *      (Stage C — settled).
 *
 * Each update sends the whole snapshot so far (mirrors ACP's replace semantics).
 */
export function streamDiff(opts: {
  id: string;
  path: string;
  oldText: string | null;
  newText: string;
  /** Dwell on the header-only state before the first content arrives, ms (default: 700). */
  headerMs?: number;
  /** Delay between subsequent content line chunks in ms (default: 140). */
  chunkMs?: number;
  /** Final status dispatched after the full content (default: 'done'). */
  finalStatus?: ToolStatus;
  /** Optional id of the parent tool call for hierarchical rendering. */
  parentId?: string;
}): ScriptStep[] {
  const {
    id,
    path,
    oldText,
    newText,
    headerMs = 700,
    chunkMs = 140,
    finalStatus = 'done',
    parentId,
  } = opts;

  const result: ScriptStep[] = [];

  // Stage A — create the row with no content yet (header only, shimmering).
  result.push({
    kind: 'call',
    fn: (api: TranscriptApi) =>
      driveEvent(api, {
        type: 'diff_start',
        id,
        path,
        oldText,
        newText: '',
        ...(parentId !== undefined ? { parentId } : {}),
      }),
  });

  // Stage B — reveal content line-by-line; each update carries the full snapshot.
  const lines = chunkText(newText, { mode: 'line' });
  let acc = '';
  for (let i = 0; i < lines.length; i++) {
    acc += lines[i];
    const snapshot = acc;
    result.push({ kind: 'wait', ms: i === 0 ? headerMs : chunkMs });
    result.push({
      kind: 'call',
      fn: (api: TranscriptApi) => driveEvent(api, { type: 'diff_update', id, newText: snapshot }),
    });
  }

  // Stage C — settle (drops the shimmer).
  result.push({ kind: 'wait', ms: chunkMs });
  result.push({
    kind: 'call',
    fn: (api: TranscriptApi) => driveEvent(api, { type: 'diff_update', id, status: finalStatus }),
  });

  return result;
}

/** A single timed update applied to a running tool call. */
export type ToolUpdateStep = {
  /** Milliseconds to wait after the previous step before applying this update. */
  afterMs: number;
  status?: ToolStatus;
  name?: string;
  inputSummary?: string;
};

/**
 * Produce steps that simulate a tool call: start immediately (synchronous),
 * then apply timed status/detail updates.
 */
export function streamTool(opts: {
  id: string;
  name: string;
  inputSummary?: string;
  /** Optional id of the parent tool call for hierarchical rendering. */
  parentId?: string;
  steps: ToolUpdateStep[];
}): ScriptStep[] {
  const { id, name, inputSummary, parentId, steps: updates } = opts;

  const result: ScriptStep[] = [];

  result.push({
    kind: 'call',
    fn: (api: TranscriptApi) =>
      driveEvent(api, {
        type: 'tool_start',
        id,
        name,
        ...(inputSummary ? { inputSummary } : {}),
        ...(parentId !== undefined ? { parentId } : {}),
      }),
  });

  for (const u of updates) {
    result.push({ kind: 'wait', ms: u.afterMs });
    result.push({
      kind: 'call',
      fn: (api: TranscriptApi) =>
        driveEvent(api, {
          type: 'tool_update',
          id,
          ...(u.status !== undefined ? { status: u.status } : {}),
          ...(u.name !== undefined ? { name: u.name } : {}),
          ...(u.inputSummary !== undefined ? { inputSummary: u.inputSummary } : {}),
        }),
    });
  }

  return result;
}

/**
 * Produce steps that simulate an execute tool call: start immediately
 * (synchronous), then apply timed status updates.
 */
export function streamExecute(opts: {
  id: string;
  command: string;
  /** Delay before the final status update in ms (default: 800). */
  durationMs?: number;
  /** Final status (default: 'done'). */
  finalStatus?: ToolStatus;
  /** Optional id of the parent tool call for hierarchical rendering. */
  parentId?: string;
}): ScriptStep[] {
  const { id, command, durationMs = 800, finalStatus = 'done', parentId } = opts;

  return [
    {
      kind: 'call',
      fn: (api: TranscriptApi) =>
        driveEvent(api, {
          type: 'execute_start',
          id,
          command,
          startedAt: Date.now(),
          ...(parentId !== undefined ? { parentId } : {}),
        }),
    },
    { kind: 'wait', ms: durationMs },
    {
      kind: 'call',
      fn: (api: TranscriptApi) =>
        driveEvent(api, { type: 'execute_update', id, status: finalStatus }),
    },
  ];
}

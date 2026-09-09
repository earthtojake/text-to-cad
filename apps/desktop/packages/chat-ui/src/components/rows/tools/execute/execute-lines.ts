/**
 * execute-lines — incremental display-line and width bookkeeping for the
 * execute row.
 *
 * Live terminal output arrives as an identity-stable lines array (the client
 * log store mutates it in place and bumps a version per flush). Both helpers
 * here key WeakMap caches on that array identity so per-update work is
 * proportional to *new* lines only:
 *
 *   executeLines        — rebuilds the display array per flush but reuses the
 *                         previous row objects for unchanged lines, so the
 *                         renderer's keyed <For> does not recreate DOM rows.
 *   maxOutputLineWidth  — natural-width overflow tracking as a running max;
 *                         committed lines are measured exactly once, only the
 *                         still-growing tail line is re-measured per call.
 */

import type { ChatExecute } from '@/model';

export type ExecuteDisplayLine = {
  kind: 'command' | 'spacer' | 'truncated' | 'output';
  text: string;
};

export const TRUNCATED_LINE_TEXT = '… earlier output truncated';

// ── Display lines ─────────────────────────────────────────────────────────────

type DisplayMemo = {
  command: string;
  version: number | undefined;
  truncated: boolean;
  lineCount: number;
  display: ExecuteDisplayLine[];
};

const displayMemo = new WeakMap<readonly string[], DisplayMemo>();

export function executeLines(item: ChatExecute): ExecuteDisplayLine[] {
  const output = item.outputLines;
  if (!output) return buildDisplay(item, [], undefined);

  const memo = displayMemo.get(output);
  if (
    memo &&
    memo.command === item.command &&
    memo.version === item.outputVersion &&
    memo.truncated === (item.outputTruncated ?? false) &&
    memo.lineCount === output.length
  ) {
    return memo.display;
  }

  const display = buildDisplay(item, output, memo?.display);
  displayMemo.set(output, {
    command: item.command,
    version: item.outputVersion,
    truncated: item.outputTruncated ?? false,
    lineCount: output.length,
    display,
  });
  return display;
}

function buildDisplay(
  item: ChatExecute,
  output: readonly string[],
  previous: ExecuteDisplayLine[] | undefined
): ExecuteDisplayLine[] {
  const next: ExecuteDisplayLine[] = [];
  const push = (kind: ExecuteDisplayLine['kind'], text: string): void => {
    const old = previous?.[next.length];
    next.push(old && old.kind === kind && old.text === text ? old : { kind, text });
  };

  const commandLines = (item.command || '…').split('\n');
  for (let i = 0; i < commandLines.length; i += 1) {
    push('command', `${i === 0 ? '$' : ' '} ${commandLines[i]}`);
  }

  // A lone empty line is the store's "no output yet" shape — render nothing.
  const hasOutput = output.length > 0 && !(output.length === 1 && output[0] === '');
  if (hasOutput || item.outputTruncated) {
    push('spacer', '');
    if (item.outputTruncated) push('truncated', TRUNCATED_LINE_TEXT);
    for (const line of output) push('output', line);
  }
  return next;
}

// ── Incremental width tracking ────────────────────────────────────────────────

export type LineWidthMeasurer = (text: string) => number;

type WidthTrack = {
  fontKey: unknown;
  committedCount: number;
  committedMax: number;
};

const widthTracks = new WeakMap<readonly string[], WidthTrack>();

/**
 * Running-max natural width over a live-appended lines array.
 *
 * All lines except the last are committed: measured once and folded into the
 * stored max. The last line is still growing (partial line), so it is measured
 * on every call but never committed. Front eviction only shrinks the array —
 * evicted lines stay in the running max by design (a scrollbar that appeared
 * never disappears mid-stream).
 */
export function maxOutputLineWidth(
  lines: readonly string[],
  fontKey: unknown,
  measure: LineWidthMeasurer
): number {
  if (lines.length === 0) return 0;

  let track = widthTracks.get(lines);
  if (!track || track.fontKey !== fontKey) {
    track = { fontKey, committedCount: 0, committedMax: 0 };
    widthTracks.set(lines, track);
  }

  const committable = lines.length - 1;
  if (track.committedCount > committable) track.committedCount = committable;
  for (let i = track.committedCount; i < committable; i += 1) {
    track.committedMax = Math.max(track.committedMax, measure(lines[i]!));
  }
  track.committedCount = committable;

  return Math.max(track.committedMax, measure(lines[lines.length - 1]!));
}

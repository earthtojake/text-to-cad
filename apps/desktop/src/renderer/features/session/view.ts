/**
 * `SessionState` → what the transcript draws. Pure, and the only place that
 * knows Codex's rendering rules (plan §2, §6):
 *
 *   - a tool call is one activity row: a glyph for its kind, one line of
 *     label, the command text inline for `execute`;
 *   - consecutive activity rows fold into one summary line — "Edited 3
 *     files, ran 2 commands" — that expands to the rows;
 *   - the live status line at the bottom of a running turn names what the
 *     agent is doing right now.
 *
 * Nothing here is React, so the folding and the labels are tested against
 * the recorded adapter transcripts without rendering anything.
 */
import type {
  Part,
  PermissionRequestPart,
  SessionState,
  SubagentPart,
  ToolCallPart,
  ToolCallStatus,
  ToolKind,
  Turn,
  TurnUsage,
} from "@shared/acp/types";

/* -------------------------------------------------------------------------- */
/* Activity rows                                                               */
/* -------------------------------------------------------------------------- */

/** The leading glyph. ACP's tool kinds plus `image` for a viewed image. */
export type Glyph = ToolKind | "image";

export type ActivityRow = {
  id: string;
  glyph: Glyph;
  /** "Edited hand.py", "Read 2 files", "Searched the web for …". Empty for a command. */
  label: string;
  /** The command text of an `execute` call, one line, for the row itself. */
  command: string | null;
  /** The path the row is about, for the tooltip and the explorer. */
  path: string | null;
  status: ToolCallStatus;
  /** Line counts over the diffs this call reported. */
  insertions: number;
  deletions: number;
  part: ToolCallPart;
};

export type ViewItem =
  | { kind: "text"; key: string; text: string; streaming: boolean }
  | { kind: "thought"; key: string; text: string; streaming: boolean }
  | {
      kind: "activity";
      key: string;
      rows: ActivityRow[];
      /** The folded line; null when the group is a single row. */
      summary: string | null;
    }
  | { kind: "permission"; key: string; part: PermissionRequestPart }
  | { kind: "subagent"; key: string; part: SubagentPart }
  | { kind: "error"; key: string; message: string }
  | { kind: "usage"; key: string; usage: TurnUsage }
  | { kind: "image"; key: string; data: string; mimeType: string }
  | { kind: "attachment"; key: string; uri: string; name: string }
  | { kind: "mode"; key: string; modeId: string };

/** The rows a turn's parts render as, folded. `open` is whether the turn is still streaming. */
export function turnView(turn: Turn, open = turn.endedAt === null): ViewItem[] {
  return partsView(turn.parts, open, turn.id);
}

export function partsView(parts: Part[], open: boolean, prefix: string): ViewItem[] {
  const items: ViewItem[] = [];
  let group: ActivityRow[] = [];

  const flush = () => {
    if (group.length === 0) {
      return;
    }
    items.push({
      kind: "activity",
      key: `${prefix}:activity:${group[0]!.id}`,
      rows: group,
      summary: group.length > 1 ? foldSummary(group) : null,
    });
    group = [];
  };

  parts.forEach((part, index) => {
    const last = index === parts.length - 1;
    const key = `${prefix}:${index}`;
    switch (part.type) {
      case "tool_call":
        group.push(activityRow(part));
        return;
      case "text":
        flush();
        if (part.text.trim() !== "") {
          items.push({ kind: "text", key, text: part.text, streaming: open && last });
        }
        return;
      case "thought":
        flush();
        if (part.text.trim() !== "") {
          items.push({ kind: "thought", key, text: part.text, streaming: open && last });
        }
        return;
      case "permission_request":
        flush();
        items.push({ kind: "permission", key, part });
        return;
      case "subagent":
        flush();
        items.push({ kind: "subagent", key, part });
        return;
      case "error":
        flush();
        items.push({ kind: "error", key, message: part.message });
        return;
      case "usage":
        flush();
        items.push({ kind: "usage", key, usage: part.usage });
        return;
      case "image":
        flush();
        items.push({ kind: "image", key, data: part.data, mimeType: part.mimeType });
        return;
      case "resource_link":
        flush();
        items.push({ kind: "attachment", key, uri: part.uri, name: part.name });
        return;
      case "mode_change":
        flush();
        items.push({ kind: "mode", key, modeId: part.modeId });
        return;
      case "plan":
      case "available_commands":
        // The plan is the pinned card above the composer; commands feed the
        // composer's palette. Neither is a transcript row.
        return;
    }
  });
  flush();
  return items;
}

export function activityRow(part: ToolCallPart): ActivityRow {
  const glyph = glyphOf(part);
  const path = pathOf(part);
  const command = glyph === "execute" ? commandOf(part) : null;
  const counts = diffTotals(part);
  return {
    id: part.id,
    glyph,
    label: command !== null && !part.title.trim() ? "" : labelOf(part, glyph, path, command !== null),
    command,
    path,
    status: part.status,
    insertions: counts.insertions,
    deletions: counts.deletions,
    part,
  };
}

/** A viewed image is an ACP `read` whose content is an image; everything else is its kind. */
function glyphOf(part: ToolCallPart): Glyph {
  if (part.content.some((content) => content.type === "image")) {
    return "image";
  }
  if (part.kind === "other" && part.content.some((content) => content.type === "diff")) {
    return "edit";
  }
  return part.kind;
}

function pathOf(part: ToolCallPart): string | null {
  const diff = part.content.find((content) => content.type === "diff");
  if (diff && diff.type === "diff") {
    return diff.path;
  }
  return part.locations[0]?.path ?? null;
}

/** The command text: the adapters put it in `rawInput.command`, then in the title. */
function commandOf(part: ToolCallPart): string | null {
  const input = part.input as { command?: unknown; cmd?: unknown } | null | undefined;
  const raw =
    typeof input?.command === "string"
      ? input.command
      : Array.isArray(input?.command)
        ? input.command.map(String).join(" ")
        : typeof input?.cmd === "string"
          ? input.cmd
          : part.title;
  const text = raw.trim();
  return text === "" ? null : text;
}

const VERBS: Record<Glyph, [done: string, doing: string, failed: string]> = {
  read: ["Read", "Reading", "Could not read"],
  edit: ["Edited", "Editing", "Could not edit"],
  delete: ["Deleted", "Deleting", "Could not delete"],
  move: ["Moved", "Moving", "Could not move"],
  search: ["Searched", "Searching", "Search failed"],
  execute: ["Ran", "Running", "Failed"],
  think: ["Thought", "Thinking", "Thinking failed"],
  fetch: ["Fetched", "Fetching", "Could not fetch"],
  switch_mode: ["Switched mode", "Switching mode", "Could not switch mode"],
  image: ["Viewed", "Viewing", "Could not view"],
  other: ["Called", "Calling", "Failed"],
};

function verb(glyph: Glyph, status: ToolCallStatus): string {
  const [done, doing, failed] = VERBS[glyph];
  return status === "failed" ? failed : status === "completed" ? done : doing;
}

function labelOf(part: ToolCallPart, glyph: Glyph, path: string | null, hasCommand: boolean): string {
  const title = part.title.trim();
  switch (glyph) {
    case "read":
    case "edit":
    case "delete":
    case "move":
    case "image":
      return path ? `${verb(glyph, part.status)} ${basename(path)}` : title || verb(glyph, part.status);
    case "execute":
      // The command is the row; a title that is not the command ("Run
      // tests") is the label in front of it.
      return hasCommand && (title === "" || title === commandOf(part)) ? "" : title;
    case "search":
    case "fetch":
      return title.startsWith(VERBS[glyph][0]) || title.startsWith(VERBS[glyph][1])
        ? title
        : title
          ? `${verb(glyph, part.status)} ${title}`
          : verb(glyph, part.status);
    case "think":
    case "switch_mode":
    case "other":
      return title || part.name || verb(glyph, part.status);
  }
}

export function basename(file: string): string {
  return file.split(/[\\/]/).filter(Boolean).pop() ?? file;
}

/** The first line of a command, trimmed, for the row; the rest shows on expand. */
export function commandLine(command: string, max = 120): string {
  const [first = "", ...rest] = command.split("\n");
  const line = first.trim().replace(/\s+/g, " ");
  const suffix = rest.some((candidate) => candidate.trim() !== "") ? " …" : "";
  return (line.length > max ? `${line.slice(0, max - 1)}…` : line) + suffix;
}

/* -------------------------------------------------------------------------- */
/* Folding                                                                     */
/* -------------------------------------------------------------------------- */

type Bucket = { glyph: Glyph; paths: Set<string>; count: number; active: boolean };

/**
 * "Edited 3 files, ran 2 commands, read hand.py" — one segment per kind in
 * order of first appearance, a single file named, progressive tense while
 * any call of that kind is still running.
 */
export function foldSummary(rows: ActivityRow[]): string {
  const buckets = new Map<Glyph, Bucket>();
  for (const row of rows) {
    let bucket = buckets.get(row.glyph);
    if (!bucket) {
      bucket = { glyph: row.glyph, paths: new Set(), count: 0, active: false };
      buckets.set(row.glyph, bucket);
    }
    bucket.count += 1;
    if (row.path) {
      bucket.paths.add(row.path);
    }
    if (row.status === "pending" || row.status === "in_progress") {
      bucket.active = true;
    }
  }
  const segments = [...buckets.values()].map(segment);
  return segments.map((text, index) => (index === 0 ? capitalize(text) : text)).join(", ");
}

const NOUNS: Record<Glyph, [singular: string, plural: string]> = {
  read: ["file", "files"],
  edit: ["file", "files"],
  delete: ["file", "files"],
  move: ["file", "files"],
  image: ["image", "images"],
  execute: ["command", "commands"],
  search: ["search", "searches"],
  fetch: ["page", "pages"],
  think: ["thought", "thoughts"],
  switch_mode: ["mode change", "mode changes"],
  other: ["tool call", "tool calls"],
};

function segment(bucket: Bucket): string {
  const [done, doing] = VERBS[bucket.glyph];
  const action = (bucket.active ? doing : done).toLowerCase();
  const files = bucket.paths.size;
  if ((bucket.glyph === "edit" || bucket.glyph === "read" || bucket.glyph === "image") && files === 1) {
    return `${action} ${basename([...bucket.paths][0]!)}`;
  }
  const n = files > 0 && bucket.glyph !== "execute" ? files : bucket.count;
  const [singular, plural] = NOUNS[bucket.glyph];
  return `${action} ${n} ${n === 1 ? singular : plural}`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/* -------------------------------------------------------------------------- */
/* Diffs                                                                       */
/* -------------------------------------------------------------------------- */

/** Lines added and removed, as a multiset difference — a badge, not a diff viewer. */
export function diffCounts(oldText: string, newText: string): { insertions: number; deletions: number } {
  const count = (text: string) => {
    const map = new Map<string, number>();
    if (text === "") {
      return map;
    }
    for (const line of text.replace(/\n$/, "").split("\n")) {
      map.set(line, (map.get(line) ?? 0) + 1);
    }
    return map;
  };
  const before = count(oldText);
  const after = count(newText);
  let insertions = 0;
  let deletions = 0;
  for (const [line, n] of after) {
    insertions += Math.max(0, n - (before.get(line) ?? 0));
  }
  for (const [line, n] of before) {
    deletions += Math.max(0, n - (after.get(line) ?? 0));
  }
  return { insertions, deletions };
}

function diffTotals(part: ToolCallPart): { insertions: number; deletions: number } {
  let insertions = 0;
  let deletions = 0;
  for (const content of part.content) {
    if (content.type === "diff") {
      const counts = diffCounts(content.oldText ?? "", content.newText);
      insertions += counts.insertions;
      deletions += counts.deletions;
    }
  }
  return { insertions, deletions };
}

/* -------------------------------------------------------------------------- */
/* Session-level views                                                         */
/* -------------------------------------------------------------------------- */

/** The italic line under a running turn: what the agent is doing right now. */
export function statusLine(state: SessionState): string | null {
  switch (state.status) {
    case "connecting":
      return "Connecting";
    case "waiting":
      return "Waiting for your approval";
    case "running":
      break;
    default:
      return null;
  }
  const turn = state.turns.at(-1);
  if (!turn || turn.role !== "agent" || turn.endedAt !== null) {
    return "Working";
  }
  const last = lastActive(turn.parts);
  if (!last) {
    return "Working";
  }
  switch (last.type) {
    case "tool_call": {
      const row = activityRow(last);
      if (row.command) {
        return `${VERBS.execute[1]} ${commandLine(row.command, 60)}`;
      }
      return row.label || VERBS[row.glyph][1];
    }
    case "thought":
      return "Thinking";
    case "subagent":
      return `${last.name} working`;
    case "text":
      // The text is on screen; a status line under it would say nothing.
      return null;
    default:
      return "Working";
  }
}

/** The last part that is still doing something, walking into subagents. */
function lastActive(parts: Part[]): Part | null {
  const last = parts.at(-1);
  if (!last) {
    return null;
  }
  if (last.type === "tool_call" && (last.status === "completed" || last.status === "failed")) {
    return last.children.length > 0 ? (lastActive(last.children) ?? last) : last;
  }
  if (last.type === "subagent" && last.state === "running" && last.parts.length > 0) {
    return lastActive(last.parts) ?? last;
  }
  return last;
}

/** "19.6k" — token counts read better rounded. */
export function formatTokens(count: number): string {
  if (count < 1_000) {
    return String(count);
  }
  if (count < 1_000_000) {
    return `${(count / 1_000).toFixed(count < 10_000 ? 1 : 0)}k`;
  }
  return `${(count / 1_000_000).toFixed(1)}M`;
}

export function formatCost(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: amount < 1 ? 3 : 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

/** "1m 12s" for the plan card and the reasoning trigger. */
export function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** The number of turns a session has, counting only what the user sent. */
export function promptCount(state: SessionState): number {
  return state.turns.filter((turn) => turn.role === "user").length;
}

export { errorMessage } from "@shared/ipc/errors";

/** True when the message names an authentication failure the user can fix by signing in. */
export function isAuthError(message: string | null | undefined): boolean {
  return /auth(entication|orization)? required|not (logged|signed) in|sign in|unauthori[sz]ed|login required/i.test(
    message ?? "",
  );
}

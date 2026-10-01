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
} from "@shared/acp/types";

import { diffCounts } from "./diff-counts";
import { basename } from "@renderer/lib/paths";

export { basename };

export { diffCounts };

/* -------------------------------------------------------------------------- */
/* Activity rows                                                               */
/* -------------------------------------------------------------------------- */

/**
 * The leading glyph. ACP's tool kinds plus `image` for a viewed image and
 * `subagent` for the call that hands work to one (Claude's `Task`, which the
 * adapter reports as a `think`).
 */
export type Glyph = ToolKind | "image" | "subagent";

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

/**
 * One row per tool call part, remembered by the part itself. The reducer
 * replaces a part when anything in it changes and keeps it otherwise, so a
 * row computed once holds until then — and a row is not cheap: its badge
 * counts the lines of every diff the call reported, and the transcript asks
 * for every row on every streamed token.
 */
const ROWS = new WeakMap<ToolCallPart, ActivityRow>();

export function activityRow(part: ToolCallPart): ActivityRow {
  let row = ROWS.get(part);
  if (!row) {
    row = computeActivityRow(part);
    ROWS.set(part, row);
  }
  return row;
}

function computeActivityRow(part: ToolCallPart): ActivityRow {
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

/**
 * A viewed image is an ACP `read` whose content is an image; a call that
 * starts a subagent is `subagent`; a `delete` that carries a shell command
 * (`rm -rf build`), or an `other` from a known shell tool, is a command,
 * because the row draws the command and a file glyph beside a terminal line
 * says the wrong thing. Everything else is its kind.
 */
function glyphOf(part: ToolCallPart): Glyph {
  if (part.content.some((content) => content.type === "image")) {
    return "image";
  }
  const hasDiff = part.content.some((content) => content.type === "diff");
  if (part.kind === "other" && hasDiff) {
    return "edit";
  }
  if (isSubagentCall(part)) {
    return "subagent";
  }
  if (!hasDiff && isShellShaped(part) && shellCommandOf(part) !== null) {
    return "execute";
  }
  return part.kind;
}

/**
 * Claude's `Task`/`Agent` tool: named so by the adapter, titled "Task: …",
 * or already holding the child's calls (the adapter routes a subagent's
 * updates into the tool call that started it).
 */
function isSubagentCall(part: ToolCallPart): boolean {
  if (part.kind !== "think" && part.kind !== "other") {
    return false;
  }
  return (
    part.name === "Task" ||
    part.name === "Agent" ||
    /^Task\b/.test(part.title.trim()) ||
    part.children.some((child) => child.type === "tool_call")
  );
}

/**
 * Shell tools by the names adapters give them. Claude's `Bash` and Codex's
 * shell already arrive as `kind: "execute"`; this is for an adapter that
 * reports one as `other`. Any other `other` with a `command` parameter —
 * an MCP tool's, say — keeps its own glyph: a parameter name is not a shell.
 */
const SHELL_TOOL_NAMES = new Set(["bash", "shell", "local_shell", "exec_command", "run_shell_command", "terminal"]);

function isShellShaped(part: ToolCallPart): boolean {
  if (part.kind === "delete") {
    return true;
  }
  if (part.kind !== "other") {
    return false;
  }
  if (part.name !== null) {
    return SHELL_TOOL_NAMES.has(part.name.toLowerCase());
  }
  // ACP's ToolCall has no name, so most adapters send none (the reducer only
  // keeps a non-standard `name`, and no `_meta` tool name). Then the title
  // decides: a shell call is titled with its own command line, as Codex
  // titles its exec calls, bare or after a `$ ` prompt. The title has to BE
  // the command — an MCP tool is titled with its tool name, and a `$ ` in
  // front of anything else is not enough.
  if (shellCommandOf(part) === null) {
    return false;
  }
  const title = part.title.trim();
  const bare = title.startsWith("$ ") ? title.slice(2).trim() : title;
  return commandForms(part).includes(bare);
}

/**
 * Every spelling of the call's command a title could be: the string itself,
 * or for an argv array its shell-quoted join, its plain join, and the script
 * of a `sh -c …` / `bash -lc …` wrapper.
 */
function commandForms(part: ToolCallPart): string[] {
  const input = part.input as { command?: unknown; cmd?: unknown } | null | undefined;
  if (typeof input?.command === "string") return [input.command.trim()];
  if (typeof input?.cmd === "string") return [input.cmd.trim()];
  if (!Array.isArray(input?.command)) return [];
  const argv = input.command.map(String);
  const forms = [shellJoin(argv), argv.join(" ")];
  const script = argv.length === 3 && /^-[a-z]*c$/.test(argv[1]!) ? argv[2]! : null;
  if (script !== null && /(^|\/)(ba|z|da|k)?sh$/.test(argv[0]!)) forms.push(script.trim());
  return forms;
}

/** argv as a shell would need it typed: shlex.join's single-quote rule. */
export function shellJoin(argv: readonly string[]): string {
  return argv
    .map((arg) => (arg !== "" && /^[\w@%+=:,./-]+$/.test(arg) ? arg : `'${arg.replace(/'/g, `'"'"'`)}'`))
    .join(" ");
}

/**
 * The editor tools also put a `command` in their input ("view",
 * "str_replace"); those are verbs, not shell lines.
 */
const EDITOR_COMMANDS = new Set(["view", "create", "str_replace", "insert", "undo_edit"]);

/** A shell command in the call's input, when there is one; the title is not consulted. */
function shellCommandOf(part: ToolCallPart): string | null {
  const input = part.input as { command?: unknown; cmd?: unknown } | null | undefined;
  const raw =
    typeof input?.command === "string"
      ? input.command
      : Array.isArray(input?.command)
        ? shellJoin(input.command.map(String))
        : typeof input?.cmd === "string"
          ? input.cmd
          : null;
  const text = raw?.trim() ?? "";
  return text === "" || EDITOR_COMMANDS.has(text) ? null : text;
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
        ? shellJoin(input.command.map(String))
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
  subagent: ["Delegated", "Delegating", "Subagent failed"],
  other: ["Called", "Calling", "Failed"],
};

function verb(glyph: Glyph, status: ToolCallStatus): string {
  const [done, doing, failed] = VERBS[glyph];
  switch (status) {
    case "failed":
      return failed;
    case "completed":
      return done;
    case "cancelled":
      // The turn stopped it mid-way: "Cancelled editing a.py".
      return `Cancelled ${doing.charAt(0).toLowerCase()}${doing.slice(1)}`;
    case "pending":
    case "in_progress":
      return doing;
  }
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
    case "subagent":
    case "switch_mode":
    case "other":
      return title || part.name || verb(glyph, part.status);
  }
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
 * any call of that kind is still running. A failed or cancelled call is not
 * running: it folds in the past tense.
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
  subagent: ["task", "tasks"],
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
      // A call the turn cancelled is nobody's current work.
      if (last.status === "cancelled") {
        return "Working";
      }
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
  if (last.type === "tool_call" && (last.status === "completed" || last.status === "failed" || last.status === "cancelled")) {
    return last.children.length > 0 ? (lastActive(last.children) ?? last) : last;
  }
  if (last.type === "subagent" && last.state === "running" && last.parts.length > 0) {
    return lastActive(last.parts) ?? last;
  }
  return last;
}

/**
 * The plan card's clock: the turn that produced the plan, on its own terms.
 * It runs only while that turn is the one running — not while any later turn
 * does — and a turn that ended says how long it took, whenever it is drawn.
 */
export function planClock(state: SessionState): { startedAt: number; endedAt: number | null; running: boolean } | null {
  const turn = state.turns.findLast(
    (candidate) => candidate.role === "agent" && candidate.parts.some((part) => part.type === "plan"),
  );
  if (!turn) {
    return null;
  }
  const running = turn.endedAt === null && (state.status === "running" || state.status === "waiting");
  return { startedAt: turn.startedAt, endedAt: turn.endedAt, running };
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

/**
 * Whether a config option is the one that says how hard to think — and, in
 * the same file, which one is the model and which mode is the agent's own
 * auto preset.
 *
 * These moved to `@shared/acp/options` when main started applying them too:
 * a session is created with the stored model and effort and in the
 * provider's auto mode, and the chips draw the same three answers. One file
 * is where the two processes agree; this re-export is so the transcript's
 * own module still reads as one surface.
 */
export { isEffortOption } from "@shared/acp/options";

export { errorMessage } from "@shared/ipc/errors";

/** True when the message names an authentication failure the user can fix by signing in. */
export function isAuthError(message: string | null | undefined): boolean {
  return /auth(entication|orization)? required|not (logged|signed) in|sign in|unauthori[sz]ed|login required/i.test(
    message ?? "",
  );
}

/**
 * Hardcore's domain types.
 *
 * Every type here is inferred from a zod schema, and the schema is the only
 * definition: the same object validates an IPC payload, a row read back out of
 * sqlite, and a settings blob written by an older version of the app. A type
 * without a schema would be a fourth place for the shape to drift.
 *
 * This module is imported by main, preload and renderer alike, so it must stay
 * free of Electron and Node imports.
 */
import { z } from "zod";

/* -------------------------------------------------------------------------- */
/* Projects                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * A project is a directory. Sessions live under projects; there are no loose
 * sessions (plan §3).
 */
export const ProjectSchema = z.object({
  id: z.string(),
  /** Display name. Defaults to the directory's basename; renameable. */
  name: z.string(),
  /** Absolute path of the directory. */
  path: z.string(),
  /** Unix milliseconds. */
  createdAt: z.number().int(),
});
export type Project = z.infer<typeof ProjectSchema>;

/* -------------------------------------------------------------------------- */
/* Sessions                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Where a session's working directory comes from (plan §9):
 * - `none`      the project directory itself, git ignored entirely;
 * - `checkout`  the project directory, on whatever branch it is already on;
 * - `worktree`  a fresh branch in a worktree under the worktree root.
 */
export const GitModeSchema = z.enum(["none", "checkout", "worktree"]);
export type GitMode = z.infer<typeof GitModeSchema>;

/** The trailing glyph on a sidebar session row. */
export const SessionStatusSchema = z.enum([
  /** The adapter is being spawned or the session loaded. */
  "connecting",
  /** No turn in flight. */
  "idle",
  /** A turn is streaming. */
  "running",
  /** The agent asked for a permission decision and is blocked on the user. */
  "waiting",
  /** The last turn ended badly; the row shows a retry. */
  "error",
  /** No adapter process; the next prompt reconnects and loads. */
  "closed",
]);
export type SessionStatus = z.infer<typeof SessionStatusSchema>;

/**
 * One thread, one agent (plan §3). The agent owns the transcript; this is the
 * index entry the app keeps so the sidebar can list threads without loading
 * them.
 */
export const SessionSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  /** Registry id of the agent bound to this session at creation. */
  agentId: z.string(),
  /** Absolute working directory the agent runs in. */
  cwd: z.string(),
  gitMode: GitModeSchema,
  /** Set when `gitMode` is `checkout` or `worktree`. */
  branch: z.string().optional(),
  /** First prompt, trimmed — Codex's convention. */
  title: z.string(),
  createdAt: z.number().int(),
  updatedAt: z.number().int(),
  status: SessionStatusSchema,
  /**
   * The agent's own id for this session, set by `session/new` and used by
   * `session/load` to resume. Null until the first successful connect.
   */
  acpSessionId: z.string().nullable().default(null),
  /**
   * Files the agent has touched in this session (edits with diffs and
   * `fs/write_text_file`), for the sidebar's files-changed pill. Line counts
   * come from the diffs the agent reported, not from git — P7 owns that.
   */
  changedFiles: z.number().int().nonnegative().default(0),
  insertions: z.number().int().nonnegative().default(0),
  deletions: z.number().int().nonnegative().default(0),
});
export type Session = z.infer<typeof SessionSchema>;

/* -------------------------------------------------------------------------- */
/* Explorer                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * The explorer is one tab strip with four kinds of tab and no bottom panel —
 * the terminal is a tab like everything else (plan §2, §7).
 */
export const ExplorerTabKindSchema = z.enum(["file", "review", "browser", "terminal"]);
export type ExplorerTabKind = z.infer<typeof ExplorerTabKindSchema>;

const ExplorerTabBase = {
  id: z.string(),
  /** The session whose explorer strip holds this tab. */
  sessionId: z.string(),
  /** Strip order, ascending. */
  order: z.number().int(),
};

/** A file, rendered by whichever renderer its extension selects. */
export const FileTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("file"),
  /** Absolute path, or null for a tab opened before a file was picked. */
  path: z.string().nullable(),
  /** Markdown opens as a preview; `View source` flips this. */
  viewSource: z.boolean().default(false),
});

/** The working tree's diff, per file. */
export const ReviewTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("review"),
  scope: z.enum(["last-turn", "all-changes"]).default("last-turn"),
});

/** An Electron `<webview>` with browser chrome. */
export const BrowserTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("browser"),
  url: z.string().nullable(),
});

/** xterm.js over a node-pty in the session's cwd. */
export const TerminalTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("terminal"),
  /** Set once the pty exists. */
  ptyId: z.string().nullable(),
  /** Agent-created ACP terminals are shown read-only with a label. */
  readOnly: z.boolean().default(false),
});

export const ExplorerTabSchema = z.discriminatedUnion("kind", [
  FileTabSchema,
  ReviewTabSchema,
  BrowserTabSchema,
  TerminalTabSchema,
]);
export type ExplorerTab = z.infer<typeof ExplorerTabSchema>;
export type FileTab = z.infer<typeof FileTabSchema>;
export type ReviewTab = z.infer<typeof ReviewTabSchema>;
export type BrowserTab = z.infer<typeof BrowserTabSchema>;
export type TerminalTab = z.infer<typeof TerminalTabSchema>;

/* -------------------------------------------------------------------------- */
/* Settings                                                                    */
/* -------------------------------------------------------------------------- */

export const ThemePreferenceSchema = z.enum(["system", "light", "dark"]);
export type ThemePreference = z.infer<typeof ThemePreferenceSchema>;

/**
 * Pane geometry, persisted so the window comes back the way it was left.
 * The three numbers are react-resizable-panels percentages and always sum to
 * 100 for the panes that are open.
 */
export const PaneLayoutSchema = z.object({
  // 16 / 39 / 45 of a 1440-wide window is a 230px sidebar and a session
  // column wide enough for a 640px transcript — Codex's proportions.
  sidebar: z.number().min(0).max(100).default(16),
  session: z.number().min(0).max(100).default(39),
  explorer: z.number().min(0).max(100).default(45),
  sidebarCollapsed: z.boolean().default(false),
  explorerCollapsed: z.boolean().default(false),
});
export type PaneLayout = z.infer<typeof PaneLayoutSchema>;

/**
 * Everything Settings can change. Every field has a default, so a settings row
 * written by an older build parses into a complete object and the app never
 * has to ask "is this undefined because it is off, or because it is new?".
 */
export const SettingsSchema = z.object({
  /* General */
  defaultProjectFolder: z.string().nullable().default(null),
  launchAtLogin: z.boolean().default(false),
  showInMenuBar: z.boolean().default(false),
  notificationsEnabled: z.boolean().default(true),
  notificationSound: z.boolean().default(false),
  /** Off by default (plan §10). Aptabase is a no-op unless this is on. */
  telemetry: z.boolean().default(false),

  /* Appearance */
  theme: ThemePreferenceSchema.default("system"),
  layout: PaneLayoutSchema.default(PaneLayoutSchema.parse({})),

  /* Agents */
  defaultAgentId: z.string().nullable().default(null),

  /* Git & worktrees */
  defaultGitMode: GitModeSchema.default("checkout"),
  worktreeRoot: z.string().nullable().default(null),
  branchPrefix: z.string().default("hardcore/"),
  fetchBeforeCreate: z.boolean().default(true),
  autoDeleteWorktrees: z.boolean().default(false),
  worktreeKeepLimit: z.number().int().min(1).default(10),
  draftPullRequests: z.boolean().default(true),

  /* CAD runtime */
  cadPythonOverride: z.string().nullable().default(null),

  /* Updates */
  checkUpdatesOnLaunch: z.boolean().default(true),
});
export type Settings = z.infer<typeof SettingsSchema>;

/** The all-defaults settings object. */
export function defaultSettings(): Settings {
  return SettingsSchema.parse({});
}

/* -------------------------------------------------------------------------- */
/* Window state                                                                */
/* -------------------------------------------------------------------------- */

/** Persisted BrowserWindow geometry. */
export const WindowStateSchema = z.object({
  x: z.number().int().optional(),
  y: z.number().int().optional(),
  width: z.number().int().positive().default(1440),
  height: z.number().int().positive().default(900),
  maximized: z.boolean().default(false),
});
export type WindowState = z.infer<typeof WindowStateSchema>;

/* -------------------------------------------------------------------------- */
/* App info                                                                    */
/* -------------------------------------------------------------------------- */

export const AppInfoSchema = z.object({
  /** The repository's VERSION, stamped at build time. */
  version: z.string(),
  platform: z.enum(["darwin", "win32", "linux"]),
  /** True in `electron-vite dev`. */
  isDev: z.boolean(),
});
export type AppInfo = z.infer<typeof AppInfoSchema>;

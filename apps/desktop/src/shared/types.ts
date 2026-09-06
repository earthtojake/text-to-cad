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

/**
 * A strip belongs to a *project*, not to a session.
 *
 * A person opening a file, a terminal and a review is looking at a directory;
 * closing a thread and starting another one in the same directory should not
 * take those away. Sessions live under projects (§3), so the project is the
 * longer-lived of the two, and it is the one the strip is keyed by.
 */
const ExplorerTabBase = {
  id: z.string(),
  projectId: z.string(),
  /** Strip order, ascending. */
  order: z.number().int(),
};

/** A file, rendered by whichever renderer its extension selects. */
export const FileTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("file"),
  /**
   * Project-root-relative path with POSIX separators, or null for a tab
   * opened before a file was picked. Relative rather than absolute so a strip
   * survives the project directory being moved.
   */
  path: z.string().nullable(),
  /** Markdown opens as a preview; `View source` flips this. */
  viewSource: z.boolean().default(false),
});

/**
 * The working tree's diff, per file.
 *
 * `all` is Codex's `All changes`; the rest are its `Since …` presets, resolved
 * against git in main. A per-turn scope arrives with P2, which knows when a
 * turn started; the shape it will use (`{ kind: "range" }`) is already in the
 * IPC contract.
 */
export const ReviewTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("review"),
  scope: z.enum(["all", "1h", "4h", "24h", "7d"]).default("all"),
});

/** An Electron `<webview>` with browser chrome. */
export const BrowserTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("browser"),
  url: z.string().nullable(),
});

/** xterm.js over a node-pty. */
export const TerminalTabSchema = z.object({
  ...ExplorerTabBase,
  kind: z.literal("terminal"),
  /** Set once the pty exists; null after a restart, when it is respawned. */
  ptyId: z.string().nullable(),
  /**
   * Absolute working directory. Null means the project root — a session that
   * runs in a worktree (§9) points its terminals at that instead.
   */
  cwd: z.string().nullable().default(null),
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
 * The accent, applied by overriding `--primary` and `--ring` on `<html>`
 * (`src/renderer/hooks/use-appearance.ts`). `neutral` is stock shadcn and
 * writes no override at all, so the default app is exactly the token set
 * `apps/viewer` ships (plan §7).
 */
export const AccentColorSchema = z.enum(["neutral", "blue", "violet", "green", "orange", "rose"]);
export type AccentColor = z.infer<typeof AccentColorSchema>;

/** Root font size, which every `rem` in the UI is a multiple of. */
export const UiFontSizeSchema = z.enum(["small", "default", "large"]);
export type UiFontSize = z.infer<typeof UiFontSizeSchema>;

/** The family Monaco, terminals and code blocks ask for first. */
export const CodeFontSchema = z.enum(["system", "jetbrains-mono"]);
export type CodeFont = z.infer<typeof CodeFontSchema>;

/**
 * What "open this file outside Hardcore" means (plan §10, General). P3's
 * explorer reads it; `custom` runs `fileOpenCommand` with the path
 * substituted for `{path}`.
 */
export const FileOpenDestinationSchema = z.enum(["reveal", "editor", "custom"]);
export type FileOpenDestination = z.infer<typeof FileOpenDestinationSchema>;

/** When the notification sound plays. */
export const NotificationSoundTimingSchema = z.enum(["always", "unfocused"]);
export type NotificationSoundTiming = z.infer<typeof NotificationSoundTimingSchema>;

/**
 * Per-agent additions to the launch line the registry declares (plan §5).
 *
 * The registry is data the app ships; this is the user's amendment to it, kept
 * out of the registry so an app update cannot overwrite it and a bad edit
 * cannot corrupt the table every other agent is read from.
 */
export const AgentOverrideSchema = z.object({
  /** Appended to `launch.args`. */
  extraArgs: z.array(z.string()).default([]),
  /** Merged over `launch.env`. */
  env: z.record(z.string(), z.string()).default({}),
});
export type AgentOverride = z.infer<typeof AgentOverrideSchema>;

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
  fileOpenDestination: FileOpenDestinationSchema.default("reveal"),
  /** The shell line `custom` runs; `{path}` is substituted. */
  fileOpenCommand: z.string().default(""),
  /** BCP-47, or `auto` to follow the OS. Only `auto` is offered so far. */
  language: z.string().default("auto"),
  launchAtLogin: z.boolean().default(false),
  showInMenuBar: z.boolean().default(false),
  notificationsEnabled: z.boolean().default(true),
  notificationSound: z.boolean().default(true),
  /** Absolute path to a sound file, or null for Hardcore's own chime. */
  notificationSoundFile: z.string().nullable().default(null),
  notificationSoundTiming: NotificationSoundTimingSchema.default("unfocused"),
  /** Hand the notification to the OS as a banner as well as showing it in-app. */
  notificationOsBanners: z.boolean().default(true),
  /**
   * On with an opt-out (plan §14). Aptabase is a no-op without a compiled-in
   * key either way, and `src/main/telemetry.ts` reads this per event, so
   * turning it off stops the next one rather than the next launch.
   */
  telemetry: z.boolean().default(true),

  /* Appearance */
  theme: ThemePreferenceSchema.default("system"),
  accentColor: AccentColorSchema.default("neutral"),
  uiFontSize: UiFontSizeSchema.default("default"),
  codeFont: CodeFontSchema.default("system"),
  reduceMotion: z.boolean().default(false),
  /** macOS vibrancy behind the sidebar. Off: it costs a compositing pass. */
  translucentSidebar: z.boolean().default(false),
  layout: PaneLayoutSchema.default(PaneLayoutSchema.parse({})),

  /* Agents */
  defaultAgentId: z.string().nullable().default(null),
  /** Keyed by registry id; an agent with no entry uses the registry's launch line. */
  agentOverrides: z.record(z.string(), AgentOverrideSchema).default({}),

  /* Git & worktrees */
  defaultGitMode: GitModeSchema.default("checkout"),
  /** Null means `~/.hardcore/worktrees` — main expands it, so the row shows the default without storing a home path. */
  worktreeRoot: z.string().nullable().default(null),
  branchPrefix: z.string().default("hardcore/"),
  fetchBeforeCreate: z.boolean().default(true),
  autoDeleteWorktrees: z.boolean().default(false),
  worktreeKeepLimit: z.number().int().min(1).default(10),
  draftPullRequests: z.boolean().default(true),
  /** Free text appended to the agent's instructions when it commits (P7). */
  commitInstructions: z.string().default(""),
  /** Free text appended to the agent's instructions when it opens a PR (P7). */
  pullRequestInstructions: z.string().default(""),

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

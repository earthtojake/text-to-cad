/**
 * Row ↔ domain-object translation. Nothing above this file writes SQL, and
 * nothing below it knows about `Project` or `Settings`.
 *
 * Every read runs the row through its zod schema. A database is a file on a
 * disk the user can edit, and a row written by a newer build is exactly the
 * case where a silent `as Project` would hand a half-formed object to the UI.
 */
import { realpathSync, statSync } from "node:fs";
import path from "node:path";

import { z } from "zod";

import { effortModelKey, effortOption } from "../../shared/acp/options";
import {
  ConfigOptionSchema,
  SessionModeSchema,
  type ConfigOption,
  type SessionMode,
} from "../../shared/acp/types";
import type { AgentOptions } from "../../shared/ipc/agent-options";
import {
  PersistedExplorerTabSchema,
  ProjectSchema,
  SessionSchema,
  SettingsSchema,
  WindowStateSchema,
  type ExplorerTab,
  type PersistedExplorerTab,
  type Project,
  type Session,
  type Settings,
  type WindowState,
} from "../../shared/types";
import { db } from "./index";

/* -------------------------------------------------------------------------- */
/* Projects                                                                    */
/* -------------------------------------------------------------------------- */

/** Projects are a projection of session directories, never stored entities. */
function directoryDescriptor(directory: string, createdAt = 0): Project {
  return ProjectSchema.parse({ id: directory, name: path.basename(directory) || directory, path: directory, createdAt });
}

export const projects = {
  list(): Project[] {
    const rows = db().prepare(
      "SELECT project_id AS directory, MIN(created_at) AS created_at FROM sessions GROUP BY project_id ORDER BY created_at, project_id",
    ).all() as { directory: string; created_at: number }[];
    // No stat here: a temporarily unmounted directory must not hide sessions.
    return rows.map(row => directoryDescriptor(row.directory, row.created_at));
  },

  /** Resolve a directory chosen for a new session, without creating anything. */
  add(directory: string): Project {
    if (!path.isAbsolute(directory)) throw new Error("Choose an absolute directory path");
    const canonical = realpathSync(directory);
    if (!statSync(canonical).isDirectory()) throw new Error("Choose a directory");
    // Older builds stored the chosen spelling (e.g. /tmp vs /private/tmp).
    // Reuse its session-derived identity instead of splitting that group.
    const existing = projects.list().find(project => {
      try { return realpathSync(project.path) === canonical; } catch { return false; }
    });
    if (existing) return existing;
    return directoryDescriptor(canonical);
  },

  /** Resolve a stable directory identity, including before the first session. */
  get(id: string): Project | null {
    // A checkout may be unmounted while its session's worktree still exists.
    // Recorded identities must remain readable, without rewriting their ids.
    const recorded = projects.list().find(project => project.id === id);
    if (recorded) return recorded;
    try { return projects.add(id); } catch { return null; }
  },
};

/* -------------------------------------------------------------------------- */
/* Sessions                                                                    */
/* -------------------------------------------------------------------------- */

type SessionRow = {
  id: string;
  project_id: string;
  agent_id: string;
  cwd: string;
  git_mode: string;
  branch: string | null;
  title: string;
  title_source: "prompt" | "agent" | "user";
  created_at: number;
  updated_at: number;
  status: string;
  acp_session_id: string | null;
  changed_files: number;
  insertions: number;
  deletions: number;
  archived: number;
  pinned: number;
  worktree_path: string | null;
  session_head: string | null;
  turn_head: string | null;
  turn_started_at: number | null;
};

const SESSION_COLUMNS =
  "id, project_id, agent_id, cwd, git_mode, branch, title, created_at, updated_at, status, " +
  "acp_session_id, changed_files, insertions, deletions, archived, pinned, " +
  "worktree_path, session_head, turn_head, turn_started_at, title_source";

const toSession = (row: SessionRow): Session =>
  SessionSchema.parse({
    id: row.id,
    projectId: row.project_id,
    agentId: row.agent_id,
    cwd: row.cwd,
    gitMode: row.git_mode,
    branch: row.branch ?? undefined,
    worktreePath: row.worktree_path ?? undefined,
    title: row.title,
    titleSource: row.title_source,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    status: row.status,
    acpSessionId: row.acp_session_id,
    changedFiles: row.changed_files,
    insertions: row.insertions,
    deletions: row.deletions,
    archived: row.archived === 1,
    pinned: row.pinned === 1,
    sessionHead: row.session_head,
    turnHead: row.turn_head,
    turnStartedAt: row.turn_started_at,
  });

export const sessions = {
  /** Newest first — the order the sidebar lists them in. */
  list(projectId?: string): Session[] {
    const rows = (
      projectId
        ? db()
            .prepare(
              `SELECT ${SESSION_COLUMNS} FROM sessions WHERE project_id = ? ORDER BY updated_at DESC`,
            )
            .all(projectId)
        : db().prepare(`SELECT ${SESSION_COLUMNS} FROM sessions ORDER BY updated_at DESC`).all()
    ) as SessionRow[];
    return rows.map(toSession);
  },

  get(id: string): Session | null {
    const row = db()
      .prepare(`SELECT ${SESSION_COLUMNS} FROM sessions WHERE id = ?`)
      .get(id) as SessionRow | undefined;
    return row ? toSession(row) : null;
  },

  upsert(session: Session): Session {
    const parsed = SessionSchema.parse(session);
    db()
      .prepare(
        `INSERT INTO sessions (${SESSION_COLUMNS})
         VALUES (@id, @projectId, @agentId, @cwd, @gitMode, @branch, @title, @createdAt, @updatedAt, @status,
                 @acpSessionId, @changedFiles, @insertions, @deletions, @archived, @pinned,
                 @worktreePath, @sessionHead, @turnHead, @turnStartedAt, @titleSource)
         ON CONFLICT(id) DO UPDATE SET
           agent_id = excluded.agent_id,
           cwd = excluded.cwd,
           git_mode = excluded.git_mode,
           branch = excluded.branch,
           title = excluded.title,
           title_source = excluded.title_source,
           updated_at = excluded.updated_at,
           status = excluded.status,
           acp_session_id = excluded.acp_session_id,
           changed_files = excluded.changed_files,
           insertions = excluded.insertions,
           deletions = excluded.deletions,
           archived = excluded.archived,
           pinned = excluded.pinned,
           worktree_path = excluded.worktree_path,
           session_head = excluded.session_head,
           turn_head = excluded.turn_head,
           turn_started_at = excluded.turn_started_at`,
      )
      .run({
        ...parsed,
        branch: parsed.branch ?? null,
        archived: parsed.archived ? 1 : 0,
        pinned: parsed.pinned ? 1 : 0,
        worktreePath: parsed.worktreePath ?? null,
      });
    return parsed;
  },

  remove(id: string): void {
    db().prepare("DELETE FROM sessions WHERE id = ?").run(id);
  },
};

/* -------------------------------------------------------------------------- */
/* Session state snapshots                                                     */
/* -------------------------------------------------------------------------- */

/**
 * The picture of a session's transcript that paints while its agent is
 * reconnecting (migration 10, `src/main/acp/snapshots.ts`).
 *
 * The JSON is parsed here and validated by the caller — this repository does
 * not know what a `SessionState` is, and the writer treats a row that no
 * longer matches the schema as a cache miss.
 */
export const sessionStates = {
  read(sessionId: string): unknown | null {
    const row = db()
      .prepare("SELECT state FROM session_state WHERE session_id = ?")
      .get(sessionId) as { state: string } | undefined;
    if (!row) {
      return null;
    }
    try {
      return JSON.parse(row.state);
    } catch {
      // Not JSON at all: the row is worse than useless, so it goes.
      sessionStates.remove(sessionId);
      return null;
    }
  },

  write(sessionId: string, json: string): void {
    db()
      .prepare(
        `INSERT INTO session_state (session_id, state, updated_at) VALUES (?, ?, ?)
         ON CONFLICT(session_id) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at`,
      )
      .run(sessionId, json, Date.now());
  },

  remove(sessionId: string): void {
    db().prepare("DELETE FROM session_state WHERE session_id = ?").run(sessionId);
  },
};

/* -------------------------------------------------------------------------- */
/* Agent options                                                               */
/* -------------------------------------------------------------------------- */

type AgentOptionsRow = {
  agent_id: string;
  options: string | null;
  modes: string | null;
  options_at: number | null;
  default_model: string | null;
  /** `{"<model value>": "<effort value>"}` (migration 9). */
  default_efforts: string | null;
  /** `{"<model value>": <the effort ConfigOption>}` (migration 9). */
  effort_options: string | null;
  default_mode: string | null;
};

const EffortsSchema = z.record(z.string(), z.string());
const EffortOptionsSchema = z.record(z.string(), ConfigOptionSchema);

/**
 * A row that no longer parses is a snapshot of an adapter that has changed
 * its wire shape. It is dropped to "never seen", which makes the next probe
 * take a fresh one — the same thing that happens on a first run, and the
 * reason this table is a cache rather than a record.
 */
const toAgentOptions = (row: AgentOptionsRow): AgentOptions => {
  const parsed = z.array(ConfigOptionSchema).safeParse(safeJson(row.options ?? "null"));
  const modes = z.array(SessionModeSchema).safeParse(safeJson(row.modes ?? "null"));
  const efforts = EffortsSchema.safeParse(safeJson(row.default_efforts ?? "null"));
  const effortOptions = EffortOptionsSchema.safeParse(safeJson(row.effort_options ?? "null"));
  return {
    agentId: row.agent_id,
    options: parsed.success ? parsed.data : [],
    modes: modes.success ? modes.data : [],
    updatedAt: parsed.success ? row.options_at : null,
    defaultModel: row.default_model,
    defaultEfforts: efforts.success ? efforts.data : {},
    effortOptions: effortOptions.success ? effortOptions.data : {},
    defaultMode: row.default_mode,
  };
};

const AGENT_OPTIONS_COLUMNS =
  "agent_id, options, modes, options_at, default_model, default_efforts, effort_options, default_mode";

export const agentOptions = {
  list(): AgentOptions[] {
    const rows = db()
      .prepare(`SELECT ${AGENT_OPTIONS_COLUMNS} FROM agent_options ORDER BY agent_id`)
      .all() as AgentOptionsRow[];
    return rows.map(toAgentOptions);
  },

  get(agentId: string): AgentOptions | null {
    const row = db()
      .prepare(`SELECT ${AGENT_OPTIONS_COLUMNS} FROM agent_options WHERE agent_id = ?`)
      .get(agentId) as AgentOptionsRow | undefined;
    return row ? toAgentOptions(row) : null;
  },

  /**
   * Replace the snapshot — options and modes together; the defaults are
   * untouched.
   *
   * The effort levels in it are also filed under the model they belong to.
   * The agent reports the effort option for whichever model the session is
   * on, so one snapshot only ever describes one model's levels and this is
   * the only place the others' survive — every model the person has run is
   * remembered, and the effort chip can offer the right list the moment the
   * model chip changes.
   */
  setOptions(agentId: string, options: ConfigOption[], modes: SessionMode[] = [], at = Date.now()): void {
    const connection = db();
    connection
      .prepare(
        `INSERT INTO agent_options (agent_id, options, modes, options_at) VALUES (?, ?, ?, ?)
         ON CONFLICT(agent_id) DO UPDATE SET options = excluded.options, modes = excluded.modes,
           options_at = excluded.options_at`,
      )
      .run(agentId, JSON.stringify(options), JSON.stringify(modes), at);
    const effort = effortOption(options);
    if (!effort) {
      return;
    }
    const merged = { ...readJsonColumn(agentId, "effort_options", EffortOptionsSchema), [effortModelKey(options)]: effort };
    connection
      .prepare("UPDATE agent_options SET effort_options = ? WHERE agent_id = ?")
      .run(JSON.stringify(merged), agentId);
  },

  /** Set the defaults given; an absent key leaves that default as it was. */
  setDefaults(agentId: string, defaults: { model?: string | null; mode?: string | null }): void {
    const connection = db();
    connection
      .prepare("INSERT INTO agent_options (agent_id) VALUES (?) ON CONFLICT(agent_id) DO NOTHING")
      .run(agentId);
    if (defaults.model !== undefined) {
      connection
        .prepare("UPDATE agent_options SET default_model = ? WHERE agent_id = ?")
        .run(defaults.model, agentId);
    }
    if (defaults.mode !== undefined) {
      connection
        .prepare("UPDATE agent_options SET default_mode = ? WHERE agent_id = ?")
        .run(defaults.mode, agentId);
    }
  },

  /**
   * The effort picked for one model, merged into that agent's map. `null`
   * forgets it, which sends the chip back to the level the agent reports.
   */
  setEffort(agentId: string, model: string, effort: string | null): void {
    const connection = db();
    connection
      .prepare("INSERT INTO agent_options (agent_id) VALUES (?) ON CONFLICT(agent_id) DO NOTHING")
      .run(agentId);
    const efforts = { ...readJsonColumn(agentId, "default_efforts", EffortsSchema) };
    if (effort === null) {
      delete efforts[model];
    } else {
      efforts[model] = effort;
    }
    connection
      .prepare("UPDATE agent_options SET default_efforts = ? WHERE agent_id = ?")
      .run(JSON.stringify(efforts), agentId);
  },
};

/**
 * One JSON column of an `agent_options` row, parsed, for the two writes that
 * merge into a map rather than replacing it. A column that no longer parses
 * reads as empty — a cache, the same as the rest of this table.
 *
 * The column name is a literal from this file, never a caller's string.
 */
function readJsonColumn<T>(
  agentId: string,
  column: "default_efforts" | "effort_options",
  schema: z.ZodType<Record<string, T>>,
): Record<string, T> {
  const row = db()
    .prepare(`SELECT ${column} AS value FROM agent_options WHERE agent_id = ?`)
    .get(agentId) as { value: string | null } | undefined;
  const parsed = schema.safeParse(safeJson(row?.value ?? "null"));
  return parsed.success ? parsed.data : {};
}

/* -------------------------------------------------------------------------- */
/* Explorer tabs                                                               */
/* -------------------------------------------------------------------------- */

type ExplorerTabRow = { id: string; session_id: string; payload: string };

export const explorerTabs = {
  /** One session's persisted strip. A stale payload cannot hide its siblings. */
  list(sessionId: string): PersistedExplorerTab[] {
    const session = sessions.get(sessionId);
    if (!session) throw new Error("No such session");
    const rows = db().prepare(
      "SELECT id, session_id, payload FROM explorer_tabs WHERE session_id = ? ORDER BY position",
    ).all(sessionId) as ExplorerTabRow[];
    return rows.flatMap(row => {
      const parsed = PersistedExplorerTabSchema.safeParse(safeJson(row.payload));
      return parsed.success && parsed.data.sessionId === sessionId && parsed.data.projectId === session.projectId
        ? [parsed.data] : [];
    });
  },

  /** Writes only the named session. Validate ownership before deleting anything. */
  replace(sessionId: string, tabs: ExplorerTab[]): PersistedExplorerTab[] {
    const session = sessions.get(sessionId);
    if (!session) throw new Error("No such session");
    if (tabs.some(tab => tab.sessionId !== sessionId || tab.projectId !== session.projectId)) {
      throw new Error("Explorer tabs belong to a different session");
    }
    const parsed = tabs.filter(tab => tab.kind !== "drawing").map(tab => PersistedExplorerTabSchema.parse(tab));
    const connection = db();
    connection.transaction(() => {
      connection.prepare("DELETE FROM explorer_tabs WHERE session_id = ?").run(sessionId);
      const insert = connection.prepare(
        "INSERT INTO explorer_tabs (id, session_id, kind, position, payload) VALUES (?, ?, ?, ?, ?)",
      );
      parsed.forEach((tab, index) => {
        insert.run(tab.id, sessionId, tab.kind, index, JSON.stringify({ ...tab, order: index }));
      });
    })();
    return parsed;
  },
};

function safeJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Settings                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * The window's own geometry rides in the settings table under a key that is
 * not part of `SettingsSchema`. Zod strips unknown keys, so it stays invisible
 * to Settings while still being one table to back up.
 */
const WINDOW_STATE_KEY = "__window";

function readRaw(): Record<string, unknown> {
  const rows = db().prepare("SELECT key, value FROM settings").all() as {
    key: string;
    value: string;
  }[];
  const raw: Record<string, unknown> = {};
  for (const row of rows) {
    try {
      raw[row.key] = JSON.parse(row.value);
    } catch {
      // A corrupt value is a value we do not have: the schema default wins.
    }
  }
  return raw;
}

function writeRaw(values: Record<string, unknown>) {
  const connection = db();
  const insert = connection.prepare(
    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
  );
  const write = connection.transaction(() => {
    for (const [key, value] of Object.entries(values)) {
      insert.run(key, JSON.stringify(value));
    }
  });
  write();
}

export const settings = {
  get(): Settings {
    return SettingsSchema.parse(readRaw());
  },

  /** Merge a partial update over what is stored and answer with the whole. */
  set(patch: Partial<Settings>): Settings {
    const next = SettingsSchema.parse({ ...readRaw(), ...patch });
    writeRaw(next as unknown as Record<string, unknown>);
    return next;
  },

  windowState(): WindowState {
    return WindowStateSchema.parse(readRaw()[WINDOW_STATE_KEY] ?? {});
  },

  setWindowState(state: WindowState): WindowState {
    const parsed = WindowStateSchema.parse(state);
    writeRaw({ [WINDOW_STATE_KEY]: parsed });
    return parsed;
  },
};

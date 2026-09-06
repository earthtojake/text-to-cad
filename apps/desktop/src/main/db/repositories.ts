/**
 * Row ↔ domain-object translation. Nothing above this file writes SQL, and
 * nothing below it knows about `Project` or `Settings`.
 *
 * Every read runs the row through its zod schema. A database is a file on a
 * disk the user can edit, and a row written by a newer build is exactly the
 * case where a silent `as Project` would hand a half-formed object to the UI.
 */
import { randomUUID } from "node:crypto";
import path from "node:path";

import {
  ExplorerTabSchema,
  ProjectSchema,
  SessionSchema,
  SettingsSchema,
  WindowStateSchema,
  type ExplorerTab,
  type Project,
  type Session,
  type Settings,
  type WindowState,
} from "../../shared/types";
import { db } from "./index";

/* -------------------------------------------------------------------------- */
/* Projects                                                                    */
/* -------------------------------------------------------------------------- */

type ProjectRow = { id: string; name: string; path: string; created_at: number };

const toProject = (row: ProjectRow): Project =>
  ProjectSchema.parse({
    id: row.id,
    name: row.name,
    path: row.path,
    createdAt: row.created_at,
  });

export const projects = {
  list(): Project[] {
    const rows = db()
      .prepare("SELECT id, name, path, created_at FROM projects ORDER BY created_at ASC")
      .all() as ProjectRow[];
    return rows.map(toProject);
  },

  byPath(directory: string): Project | null {
    const row = db()
      .prepare("SELECT id, name, path, created_at FROM projects WHERE path = ?")
      .get(directory) as ProjectRow | undefined;
    return row ? toProject(row) : null;
  },

  /**
   * Add a directory. Adding one that is already a project is not an error —
   * it answers with the existing project, because "add this folder" and "I
   * already have that folder" want the same outcome.
   */
  add(directory: string, name?: string): Project {
    const existing = projects.byPath(directory);
    if (existing) {
      return existing;
    }
    const project: Project = {
      id: randomUUID(),
      name: name ?? path.basename(directory) ?? directory,
      path: directory,
      createdAt: Date.now(),
    };
    db()
      .prepare("INSERT INTO projects (id, name, path, created_at) VALUES (?, ?, ?, ?)")
      .run(project.id, project.name, project.path, project.createdAt);
    return project;
  },

  rename(id: string, name: string): Project {
    db().prepare("UPDATE projects SET name = ? WHERE id = ?").run(name, id);
    const row = db()
      .prepare("SELECT id, name, path, created_at FROM projects WHERE id = ?")
      .get(id) as ProjectRow | undefined;
    if (!row) {
      throw new Error(`no such project: ${id}`);
    }
    return toProject(row);
  },

  /** Forgets the project and its sessions. The directory is never touched. */
  remove(id: string): void {
    db().prepare("DELETE FROM projects WHERE id = ?").run(id);
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
  created_at: number;
  updated_at: number;
  status: string;
};

const SESSION_COLUMNS =
  "id, project_id, agent_id, cwd, git_mode, branch, title, created_at, updated_at, status";

const toSession = (row: SessionRow): Session =>
  SessionSchema.parse({
    id: row.id,
    projectId: row.project_id,
    agentId: row.agent_id,
    cwd: row.cwd,
    gitMode: row.git_mode,
    branch: row.branch ?? undefined,
    title: row.title,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    status: row.status,
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
         VALUES (@id, @projectId, @agentId, @cwd, @gitMode, @branch, @title, @createdAt, @updatedAt, @status)
         ON CONFLICT(id) DO UPDATE SET
           agent_id = excluded.agent_id,
           cwd = excluded.cwd,
           git_mode = excluded.git_mode,
           branch = excluded.branch,
           title = excluded.title,
           updated_at = excluded.updated_at,
           status = excluded.status`,
      )
      .run({ ...parsed, branch: parsed.branch ?? null });
    return parsed;
  },

  remove(id: string): void {
    db().prepare("DELETE FROM sessions WHERE id = ?").run(id);
  },
};

/* -------------------------------------------------------------------------- */
/* Explorer tabs                                                               */
/* -------------------------------------------------------------------------- */

type ExplorerTabRow = { id: string; project_id: string; payload: string };

export const explorerTabs = {
  /**
   * A project's strip, in order.
   *
   * A row that no longer parses is dropped rather than thrown on: the payload
   * is a JSON blob written by whichever build was running, and one stale tab
   * must not cost the person the other five.
   */
  list(projectId: string): ExplorerTab[] {
    const rows = db()
      .prepare(
        "SELECT id, project_id, payload FROM explorer_tabs WHERE project_id = ? ORDER BY position",
      )
      .all(projectId) as ExplorerTabRow[];
    return rows.flatMap((row) => {
      const parsed = ExplorerTabSchema.safeParse(safeJson(row.payload));
      return parsed.success ? [parsed.data] : [];
    });
  },

  /** Replaces a project's whole strip — the only write the UI ever needs. */
  replace(projectId: string, tabs: ExplorerTab[]): ExplorerTab[] {
    const parsed = tabs.map((tab) => ExplorerTabSchema.parse(tab));
    const connection = db();
    const write = connection.transaction(() => {
      connection.prepare("DELETE FROM explorer_tabs WHERE project_id = ?").run(projectId);
      const insert = connection.prepare(
        "INSERT INTO explorer_tabs (id, project_id, kind, position, payload) VALUES (?, ?, ?, ?, ?)",
      );
      parsed.forEach((tab, index) => {
        insert.run(tab.id, projectId, tab.kind, index, JSON.stringify({ ...tab, order: index }));
      });
    });
    write();
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

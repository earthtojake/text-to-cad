import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import Database from 'better-sqlite3';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { initializeDatabase } from '@main/db/initialize';

/**
 * Replays a populated released database through the entire unreleased chain.
 *
 * Migrations 0000–0019 are byte-identical to the released chain (see
 * migration-identity.test.ts), so applying exactly those and inserting rows
 * against the resulting schema reproduces a real user's database at the
 * released tip. The baseline is generated here — no checked-in fixture —
 * then initializeDatabase() applies everything after 0019 with the same
 * runner the production app uses.
 *
 * Assertions are invariants, not row-for-row snapshots, so future migrations
 * extend this test rather than rewrite it:
 * - every ssh_connections row and ID survives verbatim (should_connect NULL),
 * - every live project links to a repository workspace row carrying the
 *   original host identity (ssh_connection_id, location, path),
 * - conversations are seeded with host identity per the 0036 data train,
 * - the whole chain applies without error on populated data.
 */

const RELEASED_TIP_IDX = 19;
const RELEASED_TIP_TAG = '0019_eager_meteorite';

const appRoot = fileURLToPath(new URL('../../../../../', import.meta.url));
const drizzleDir = join(appRoot, 'drizzle');

type JournalEntry = { idx: number; when: number; tag: string };

/**
 * Applies migrations 0000–0019 to an empty database and records them in
 * __drizzle_migrations exactly like the production runner, so a later
 * initializeDatabase() call picks up at 0020.
 */
function applyReleasedChain(sqlite: Database.Database): void {
  const journal = JSON.parse(readFileSync(join(drizzleDir, 'meta/_journal.json'), 'utf8')) as {
    entries: JournalEntry[];
  };
  const released = journal.entries.filter((entry) => entry.idx <= RELEASED_TIP_IDX);
  expect(released).toHaveLength(RELEASED_TIP_IDX + 1);
  expect(released.at(-1)?.tag).toBe(RELEASED_TIP_TAG);

  sqlite.exec(`
    CREATE TABLE IF NOT EXISTS __drizzle_migrations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      hash TEXT NOT NULL,
      created_at NUMERIC
    )
  `);

  sqlite.pragma('foreign_keys = OFF');
  try {
    sqlite.transaction(() => {
      for (const entry of released) {
        const sql = readFileSync(join(drizzleDir, `${entry.tag}.sql`), 'utf8');
        for (const stmt of sql.split('--> statement-breakpoint')) {
          const trimmed = stmt.trim();
          if (trimmed) sqlite.exec(trimmed);
        }
        sqlite
          .prepare('INSERT INTO __drizzle_migrations (hash, created_at) VALUES (?, ?)')
          .run(createHash('sha256').update(sql).digest('hex'), entry.when);
      }
    })();
  } finally {
    sqlite.pragma('foreign_keys = ON');
  }
}

const T0 = '2026-01-15 10:00:00';

/**
 * One connection per metadata schema version (v0 unversioned through v3)
 * across all three auth types, plus a NULL-metadata row. Metadata is stored
 * as the exact JSON text a released install would carry; no migration parses
 * it, so it must survive byte-identical.
 */
const BASELINE_CONNECTIONS = [
  {
    id: 'conn-password-v0',
    name: 'legacy-box',
    host: 'legacy.example.com',
    port: 22,
    username: 'dev',
    auth_type: 'password',
    private_key_path: null,
    use_agent: 0,
    metadata: '{"sshConfigAlias":"legacy-box","forwardAgent":true}',
    created_at: T0,
    updated_at: T0,
  },
  {
    id: 'conn-key-v1',
    name: 'build-server',
    host: 'build.example.com',
    port: 2222,
    username: 'ci',
    auth_type: 'key',
    private_key_path: '/home/dev/.ssh/id_ed25519',
    use_agent: 0,
    metadata:
      '{"version":"1","proxyJump":"bastion.example.com",' +
      '"dependencySelections":{"claude-code":{"path":"/usr/local/bin/claude"}}}',
    created_at: T0,
    updated_at: T0,
  },
  {
    id: 'conn-agent-v2',
    name: 'staging',
    host: 'staging.example.com',
    port: 22,
    username: 'deploy',
    auth_type: 'agent',
    private_key_path: null,
    use_agent: 1,
    metadata:
      '{"version":"2","dependencySelections":' +
      '{"codex":{"kind":"method","method":"npm"},"claude-code":null}}',
    created_at: T0,
    updated_at: T0,
  },
  {
    id: 'conn-key-v3',
    name: 'gpu-box',
    host: 'gpu.example.com',
    port: 22,
    username: 'ml',
    auth_type: 'key',
    private_key_path: '/home/dev/.ssh/id_rsa',
    use_agent: 0,
    metadata:
      '{"version":"3","forwardAgent":false,"dependencySelections":' +
      '{"claude-code":{"kind":"pinned","realpath":"/opt/agents/claude"}}}',
    created_at: T0,
    updated_at: T0,
  },
  {
    id: 'conn-agent-no-metadata',
    name: 'bare-host',
    host: 'bare.example.com',
    port: 22,
    username: 'root',
    auth_type: 'agent',
    private_key_path: null,
    use_agent: 0,
    metadata: null,
    created_at: T0,
    updated_at: T0,
  },
] as const;

const PROJECT_LOCAL_ID = 'project-local-alpha';
const PROJECT_REMOTE_LINKED_ID = 'project-remote-beta';
const PROJECT_REMOTE_UNLINKED_ID = 'project-remote-gamma';

const REMOTE_LINKED_CONNECTION_ID = 'conn-key-v1';
const REMOTE_UNLINKED_CONNECTION_ID = 'conn-agent-v2';

const WS_REPO_BETA_ID = 'ws-repo-beta';
const WS_WORKTREE_ALPHA_ID = 'ws-worktree-alpha';
const WS_WORKTREE_BETA_ID = 'ws-worktree-beta';

const TASK_ALPHA_ID = 'task-alpha';
const TASK_BETA_ID = 'task-beta';
const TASK_GAMMA_ID = 'task-gamma';

const CONVERSATION_ALPHA_ID = 'conversation-alpha';
const CONVERSATION_BETA_ID = 'conversation-beta';
const CONVERSATION_GAMMA_ID = 'conversation-gamma';

/** Inserts representative released-era rows directly against the 0019 schema. */
function seedReleasedData(sqlite: Database.Database): void {
  const insertConnection = sqlite.prepare(
    `INSERT INTO ssh_connections
       (id, name, host, port, username, auth_type, private_key_path, use_agent,
        metadata, created_at, updated_at)
     VALUES
       (@id, @name, @host, @port, @username, @auth_type, @private_key_path, @use_agent,
        @metadata, @created_at, @updated_at)`
  );
  for (const row of BASELINE_CONNECTIONS) insertConnection.run(row);

  // A remote project's repository workspace row of the released era: type set,
  // but kind/location/ssh_connection_id unpopulated — the 0030 backfill and
  // 0032 host-identity train must fill them from the owning project.
  sqlite
    .prepare(
      `INSERT INTO workspaces (id, type, path, created_at, updated_at)
       VALUES (?, 'project-ssh', '/srv/repos/beta', ?, ?)`
    )
    .run(WS_REPO_BETA_ID, T0, T0);

  const insertProject = sqlite.prepare(
    `INSERT INTO projects
       (id, name, path, workspace_provider, base_ref, ssh_connection_id,
        repository_workspace_id, created_at, updated_at)
     VALUES (?, ?, ?, ?, 'main', ?, ?, ?, ?)`
  );
  insertProject.run(
    PROJECT_LOCAL_ID,
    'alpha',
    '/home/dev/projects/alpha',
    'local',
    null,
    null,
    T0,
    T0
  );
  insertProject.run(
    PROJECT_REMOTE_LINKED_ID,
    'beta',
    '/srv/repos/beta',
    'ssh',
    REMOTE_LINKED_CONNECTION_ID,
    WS_REPO_BETA_ID,
    T0,
    T0
  );
  // No repository workspace row anywhere — 0032 must create and link one.
  insertProject.run(
    PROJECT_REMOTE_UNLINKED_ID,
    'gamma',
    '/srv/repos/gamma',
    'ssh',
    REMOTE_UNLINKED_CONNECTION_ID,
    null,
    T0,
    T0
  );

  const insertWorktree = sqlite.prepare(
    `INSERT INTO workspaces (id, type, path, branch_name, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  );
  insertWorktree.run(
    WS_WORKTREE_ALPHA_ID,
    'local',
    '/home/dev/projects/alpha-worktrees/feat-x',
    'feat/x',
    T0,
    T0
  );
  insertWorktree.run(
    WS_WORKTREE_BETA_ID,
    'project-ssh',
    '/srv/repos/beta-worktrees/feat-y',
    'feat/y',
    T0,
    T0
  );

  const insertTask = sqlite.prepare(
    `INSERT INTO tasks
       (id, project_id, name, status, task_branch, workspace_id,
        created_at, updated_at, status_changed_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );
  insertTask.run(
    TASK_ALPHA_ID,
    PROJECT_LOCAL_ID,
    'Local task',
    'in_progress',
    'feat/x',
    WS_WORKTREE_ALPHA_ID,
    T0,
    T0,
    T0
  );
  insertTask.run(
    TASK_BETA_ID,
    PROJECT_REMOTE_LINKED_ID,
    'Remote task with worktree',
    'review',
    'feat/y',
    WS_WORKTREE_BETA_ID,
    T0,
    T0,
    T0
  );
  insertTask.run(
    TASK_GAMMA_ID,
    PROJECT_REMOTE_UNLINKED_ID,
    'Remote task without workspace',
    'todo',
    null,
    null,
    T0,
    T0,
    T0
  );

  const insertConversation = sqlite.prepare(
    `INSERT INTO conversations
       (id, project_id, task_id, title, provider, is_initial_conversation,
        session_id, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)`
  );
  insertConversation.run(
    CONVERSATION_ALPHA_ID,
    PROJECT_LOCAL_ID,
    TASK_ALPHA_ID,
    'Local conversation',
    'anthropic',
    'sess-alpha',
    T0,
    T0
  );
  insertConversation.run(
    CONVERSATION_BETA_ID,
    PROJECT_REMOTE_LINKED_ID,
    TASK_BETA_ID,
    'Remote conversation',
    'anthropic',
    'sess-beta',
    T0,
    T0
  );
  insertConversation.run(
    CONVERSATION_GAMMA_ID,
    PROJECT_REMOTE_UNLINKED_ID,
    TASK_GAMMA_ID,
    'Remote conversation without session',
    'codex',
    null,
    T0,
    T0
  );
}

describe('populated 0019 database replayed through the unreleased chain', () => {
  let sqlite: Database.Database;

  // Built once: every assertion below is read-only over the migrated database.
  beforeAll(async () => {
    sqlite = new Database(':memory:');
    applyReleasedChain(sqlite);
    seedReleasedData(sqlite);
    await initializeDatabase(sqlite);
  });

  afterAll(() => {
    sqlite?.close();
  });

  it('applies the full chain on populated released data without error', () => {
    const journal = JSON.parse(readFileSync(join(drizzleDir, 'meta/_journal.json'), 'utf8')) as {
      entries: JournalEntry[];
    };
    const applied = sqlite.prepare(`SELECT count(*) AS n FROM __drizzle_migrations`).get() as {
      n: number;
    };
    expect(applied.n).toBe(journal.entries.length);
    expect(journal.entries.length).toBeGreaterThan(RELEASED_TIP_IDX + 1);

    expect(sqlite.prepare(`PRAGMA foreign_key_check`).all()).toEqual([]);
  });

  it('preserves every ssh_connections row and ID verbatim', () => {
    // Explicit released columns (not SELECT *) so future additive columns
    // extend this test instead of breaking it.
    const rows = sqlite
      .prepare(
        `SELECT id, name, host, port, username, auth_type, private_key_path,
                use_agent, metadata, created_at, updated_at
         FROM ssh_connections ORDER BY id`
      )
      .all();

    const expected = [...BASELINE_CONNECTIONS]
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((row) => ({ ...row }));
    expect(rows).toEqual(expected);
  });

  it('leaves legacy connections with should_connect NULL (auto-connect intent)', () => {
    const rows = sqlite.prepare(`SELECT id, should_connect FROM ssh_connections`).all() as Array<{
      id: string;
      should_connect: number | null;
    }>;
    expect(rows).toHaveLength(BASELINE_CONNECTIONS.length);
    for (const row of rows) {
      expect(row.should_connect, `should_connect for ${row.id}`).toBeNull();
    }
  });

  it('links every live project to a repository workspace row with its original host identity', () => {
    const rows = sqlite
      .prepare(
        `SELECT projects.id AS project_id, workspaces.id AS workspace_id,
                workspaces.kind, workspaces.location, workspaces.ssh_connection_id,
                workspaces.path
         FROM projects
         INNER JOIN workspaces ON workspaces.id = projects.repository_workspace_id
         WHERE projects.deleted_at IS NULL`
      )
      .all() as Array<{
      project_id: string;
      workspace_id: string;
      kind: string;
      location: string;
      ssh_connection_id: string | null;
      path: string;
    }>;

    expect(rows).toHaveLength(3);
    const byProject = new Map(rows.map((row) => [row.project_id, row]));

    expect(byProject.get(PROJECT_LOCAL_ID)).toMatchObject({
      kind: 'repository',
      location: 'local',
      ssh_connection_id: null,
      path: '/home/dev/projects/alpha',
    });
    // The pre-existing repository row keeps its identity and gains the host
    // linkage that lived on the project before the 0033 column drops.
    expect(byProject.get(PROJECT_REMOTE_LINKED_ID)).toMatchObject({
      workspace_id: WS_REPO_BETA_ID,
      kind: 'repository',
      location: 'remote',
      ssh_connection_id: REMOTE_LINKED_CONNECTION_ID,
      path: '/srv/repos/beta',
    });
    // The project without any repository row gets one created for it.
    expect(byProject.get(PROJECT_REMOTE_UNLINKED_ID)).toMatchObject({
      kind: 'repository',
      location: 'remote',
      ssh_connection_id: REMOTE_UNLINKED_CONNECTION_ID,
      path: '/srv/repos/gamma',
    });
  });

  it('carries host identity onto remote worktree workspace rows', () => {
    const worktree = sqlite
      .prepare(`SELECT location, ssh_connection_id FROM workspaces WHERE id = ?`)
      .get(WS_WORKTREE_BETA_ID) as { location: string; ssh_connection_id: string | null };
    expect(worktree).toEqual({
      location: 'remote',
      ssh_connection_id: REMOTE_LINKED_CONNECTION_ID,
    });
  });

  it('seeds conversations with host identity from the owning project (0036 semantics)', () => {
    const rows = sqlite
      .prepare(
        `SELECT id, location, ssh_connection_id, provider_session_id,
                observed_status, origin, untracked_at
         FROM conversations ORDER BY id`
      )
      .all() as Array<{
      id: string;
      location: string;
      ssh_connection_id: string | null;
      provider_session_id: string | null;
      observed_status: string;
      origin: string;
      untracked_at: string | null;
    }>;

    expect(rows).toHaveLength(3);
    const byId = new Map(rows.map((row) => [row.id, row]));

    expect(byId.get(CONVERSATION_ALPHA_ID)).toMatchObject({
      location: 'local',
      ssh_connection_id: null,
      provider_session_id: 'sess-alpha',
    });
    expect(byId.get(CONVERSATION_BETA_ID)).toMatchObject({
      location: 'remote',
      ssh_connection_id: REMOTE_LINKED_CONNECTION_ID,
      provider_session_id: 'sess-beta',
    });
    expect(byId.get(CONVERSATION_GAMMA_ID)).toMatchObject({
      location: 'remote',
      ssh_connection_id: REMOTE_UNLINKED_CONNECTION_ID,
      provider_session_id: null,
    });

    // Every released conversation enters the registry as a live, registered row.
    for (const row of rows) {
      expect(row.observed_status, `observed_status for ${row.id}`).toBe('present');
      expect(row.origin, `origin for ${row.id}`).toBe('registered');
      expect(row.untracked_at, `untracked_at for ${row.id}`).toBeNull();
    }
  });

  it('keeps all tasks alive and bound to their projects', () => {
    const rows = sqlite
      .prepare(`SELECT id, project_id, deleted_at FROM tasks WHERE deleted_at IS NULL ORDER BY id`)
      .all() as Array<{ id: string; project_id: string }>;
    expect(rows.map((row) => row.id)).toEqual([TASK_ALPHA_ID, TASK_BETA_ID, TASK_GAMMA_ID]);
  });
});

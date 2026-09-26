import { execFileSync } from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication } from "@playwright/test";
import { MIGRATIONS } from "../../src/main/db/migrations";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const require = createRequire(path.join(appRoot, "package.json"));
const electronBinary = require("electron") as string;

/** Real SQLite under Electron's ABI; no window or user's database involved. */
function sqlScript(database: string, body: string, args: unknown = null): unknown {
  const script = `const Database = require(${JSON.stringify(require.resolve("better-sqlite3"))});
    const db = new Database(process.argv[1]);
    db.pragma('foreign_keys = ON');
    const args = JSON.parse(process.argv[2]);
    ${body}
    db.close();`;
  const output = execFileSync(electronBinary, ["-e", script, database, JSON.stringify(args)], {
    env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" }, encoding: "utf8",
  });
  return output.trim() ? JSON.parse(output) : null;
}

test("upgrade preserves sessions, snapshots and owned tabs; restart and deletion stay isolated", async () => {
  test.setTimeout(120_000);
  const scratch = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-storage-")));
  const profile = path.join(scratch, "profile");
  const directory = path.join(scratch, "project");
  const worktree = path.join(scratch, "worktree");
  for (const dir of [profile, directory, worktree]) fs.mkdirSync(dir);
  const database = path.join(profile, "hardcore.db");
  // A real pre-upgrade database: shared tabs, archived and pinned sessions,
  // agent ids, worktree metadata, snapshots and unrelated settings.
  sqlScript(database, `
    for (const migration of args.migrations) db.exec(migration.up);
    db.pragma('user_version = 10');
    db.prepare('INSERT INTO projects VALUES (?, ?, ?, ?)').run('old-project', 'Renamed project', args.directory, 1);
    const insert = db.prepare("INSERT INTO sessions (id,project_id,agent_id,cwd,git_mode,title,created_at,updated_at,status,acp_session_id,archived,pinned,worktree_path,session_head,turn_head) VALUES (?, 'old-project','claude-code',?,'none',?,1,?,'closed',?, ?, ?, ?, 'head','turn')");
    insert.run('one', args.directory, 'First session', 10, 'remote-one', 0, 1, null);
    insert.run('two', args.worktree, 'Second session', 20, 'remote-two', 0, 0, args.worktree);
    insert.run('archived', args.directory, 'Archived session', 30, 'remote-archived', 1, 0, null);
    db.prepare('INSERT INTO session_state VALUES (?, ?, ?)').run('one', '{"preserved":"snapshot"}', 10);
    db.prepare('INSERT INTO settings VALUES (?, ?)').run('theme', '"dark"');
    for (const [id, root] of [['checkout-tab', null], ['worktree-tab', args.worktree]]) {
      db.prepare('INSERT INTO explorer_tabs VALUES (?, ?, ?, ?, ?)').run(id, 'old-project', 'file', 0,
        JSON.stringify({ id, projectId:'old-project', kind:'file', order:0, root, path:null, panel:null }));
    }
  `, { migrations: MIGRATIONS.slice(0, 10), directory, worktree });
  let app: ElectronApplication | null = null;
  const launch = async () => {
    app = await electron.launch({
      args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${profile}`],
      env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") },
    });
    const page = await app.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    return page;
  };
  try {
    let page = await launch();
    const rows = await page.evaluate(() => window.hardcore.sessions.list({}));
    expect(rows.map(row => row.id).sort()).toEqual(["archived", "one", "two"]);
    expect(rows.find(row => row.id === "one")).toMatchObject({ projectId: directory, acpSessionId: "remote-one", pinned: true });
    expect(rows.find(row => row.id === "two")).toMatchObject({ worktreePath: worktree, sessionHead: "head", turnHead: "turn" });
    expect(rows.find(row => row.id === "archived")?.archived).toBe(true);
    const tabs = await page.evaluate(async () => ({
      one: await window.hardcore.explorer.loadTabs({ sessionId: "one" }),
      two: await window.hardcore.explorer.loadTabs({ sessionId: "two" }),
    }));
    expect(tabs.one.map(tab => tab.id)).toEqual(["checkout-tab"]);
    expect(tabs.two.map(tab => tab.id)).toEqual(["worktree-tab"]);
    expect(tabs.one[0]).toMatchObject({ sessionId: "one", projectId: directory });
    expect(await page.evaluate(async (tab) => {
      try { await window.hardcore.explorer.saveTabs({ sessionId: "two", tabs: [tab] }); return "accepted"; }
      catch { return "refused"; }
    }, tabs.one[0]!)).toBe("refused");
    // A new session in that same directory inherits no tab state.
    const fresh = await page.evaluate(projectId => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "none" }), directory);
    expect(await page.evaluate(sessionId => window.hardcore.explorer.loadTabs({ sessionId }), fresh.id)).toEqual([]);
    await page.evaluate(() => window.hardcore.sessions.delete({ id: "two" }));
    expect(await page.evaluate(() => window.hardcore.explorer.loadTabs({ sessionId: "one" }))).toEqual(tabs.one);
    await app!.close(); app = null;

    const backups = fs.readdirSync(profile).filter(name => name.includes(".before-v11-"));
    expect(backups).toHaveLength(1);
    expect(sqlScript(path.join(profile, backups[0]!), "console.log(JSON.stringify(db.prepare('SELECT count(*) AS count FROM sessions').get()))")).toEqual({ count: 3 });
    expect(sqlScript(database, `console.log(JSON.stringify({
      projects: db.prepare("SELECT name FROM sqlite_master WHERE name='projects'").all(),
      snapshots: db.prepare('SELECT state FROM session_state WHERE session_id=?').get('one'),
      foreignKeys: db.pragma('foreign_key_check'),
      theme: db.prepare("SELECT value FROM settings WHERE key='theme'").get(),
    }))`)).toEqual({ projects: [], snapshots: { state: '{"preserved":"snapshot"}' }, foreignKeys: [], theme: { value: '"dark"' } });

    page = await launch();
    const after = await page.evaluate(() => window.hardcore.sessions.list({}));
    expect(after.map(row => row.id).sort()).toEqual(["archived", "one", fresh.id].sort());
    expect(await page.evaluate(() => window.hardcore.explorer.loadTabs({ sessionId: "one" }))).toEqual(tabs.one);
    // Archiving never destroys a row and restoring needs no project creation.
    await page.evaluate(() => window.hardcore.sessions.archive({ id: "one", archived: true }));
    await page.evaluate(() => window.hardcore.sessions.archive({ id: "one", archived: false }));
    expect(await page.evaluate(() => window.hardcore.sessions.get({ id: "one" }))).toMatchObject({ archived: false, projectId: directory });
  } finally {
    await (app as ElectronApplication | null)?.close();
    fs.rmSync(scratch, { recursive: true, force: true });
  }
});

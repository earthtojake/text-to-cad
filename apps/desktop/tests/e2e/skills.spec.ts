import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * What the app gives an agent (plan §8, as revised): the skills root in every
 * `session/new`, the preamble only for an agent that will not read one, the
 * `hardcore` MCP server's two skills tools, and the bundled runtime's `cadgen`
 * on the session's PATH. Nothing is installed into any agent's own
 * configuration — there is no plugin.
 *
 * The fake agent appends a JSON line for every `session/new`, `session/load`
 * and prompt it is given, and for the two turns this suite drives
 * (`FAKE_AGENT_RECORD`), so what is asserted here is the wire and not the UI.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: { theme?: string }): Promise<unknown> };
    skills: { info(): Promise<{ root: string | null; skills: { name: string; description: string }[] }> };
    sessions: {
      create(input: { projectId: string; agentId: string; cwd: string; gitMode: "none" }): Promise<{ id: string }>;
      prompt(input: { id: string; content: { type: "text"; text: string }[] }): Promise<{ stopReason: string }>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

type Frame = { kind: string; params: Record<string, unknown> };

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let projectId: string;
let recordFile: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-skills-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-skills-project-"));
  fs.writeFileSync(path.join(project, "README.md"), "# Scratch\n");
  recordFile = path.join(userData, "frames.jsonl");

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: {
      ...process.env,
      NODE_ENV: "test",
      HARDCORE_FAKE_AGENT: fakeAgent,
      FAKE_AGENT_RECORD: recordFile,
    },
  });
  page = await app.firstWindow();
  page.on("pageerror", (error) => console.error(`[renderer] ${error.message}`));
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  projectId = (await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project)).id;
});

test.afterAll(async () => {
  await app?.close();
  for (const dir of [userData, project]) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

function frames(): Frame[] {
  if (!fs.existsSync(recordFile)) {
    return [];
  }
  return fs
    .readFileSync(recordFile, "utf8")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Frame);
}

/** One session with this agent, prompted in turn; the frames it produced. */
async function run(agentId: string, prompts: string[]): Promise<Frame[]> {
  const before = frames().length;
  const sessionId = await page.evaluate(
    async ({ id, agent, cwd }) => {
      const session = await window.hardcore.sessions.create({ projectId: id, agentId: agent, cwd, gitMode: "none" });
      return session.id;
    },
    { id: projectId, agent: agentId, cwd: project },
  );
  for (const text of prompts) {
    await page.evaluate(
      ({ id, content }) => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text: content }] }),
      { id: sessionId, content: text },
    );
  }
  return frames().slice(before);
}

test("the skills root exists in both layouts and is named in session/new", async () => {
  const info = await page.evaluate(() => window.hardcore.skills.info());
  expect(info.root).not.toBeNull();
  expect(info.skills.map((skill) => skill.name)).toContain("cad");
  expect(info.skills.map((skill) => skill.name)).toContain("hardcore-app-use");
  // One directory per app version, under the app's own user-data directory.
  // (Realpath'd: Electron resolves `--user-data-dir`, and /var is a link.)
  expect(path.dirname(info.root!)).toBe(path.join(fs.realpathSync(userData), "skills"));

  const sent = await run("claude-code", ["hello"]);
  const created = sent.find((frame) => frame.kind === "session/new")!;
  expect(created.params.additionalDirectories).toEqual([info.root]);
  expect(created.params._meta).toMatchObject({ additionalRoots: [info.root] });

  // Both spellings name a directory that really holds the skills, laid out
  // the way each native loader reads them.
  for (const layout of [path.join(".claude", "skills"), path.join(".agents", "skills")]) {
    expect(fs.existsSync(path.join(info.root!, layout, "cad", "SKILL.md"))).toBe(true);
    expect(fs.existsSync(path.join(info.root!, layout, "hardcore-app-use", "SKILL.md"))).toBe(true);
  }
});

test("an agent that does not load the root gets the preamble once, and a native one never", async () => {
  // gemini-cli's ACP `newSession` ignores additional directories.
  const told = await run("gemini-cli", ["first", "second"]);
  const prompts = told.filter((frame) => frame.kind === "prompt");
  expect(prompts).toHaveLength(2);
  const first = JSON.stringify(prompts[0]!.params.prompt);
  expect(first).toContain("whose skills are at");
  expect(first).toContain("cad/SKILL.md");
  expect(first).toContain("first");
  expect(JSON.stringify(prompts[1]!.params.prompt)).not.toContain("whose skills are at");

  // Claude Code loads the root itself, so its transcript is the person's words.
  const native = await run("claude-code", ["first", "second"]);
  for (const prompt of native.filter((frame) => frame.kind === "prompt")) {
    expect(JSON.stringify(prompt.params.prompt)).not.toContain("whose skills are at");
  }
});

test("list_skills and read_skill reach the same root through the MCP server", async () => {
  const info = await page.evaluate(() => window.hardcore.skills.info());
  const sent = await run("claude-code", ["skills"]);

  const answer = sent.find((frame) => frame.kind === "skills");
  expect(answer, "the fake agent's list_skills/read_skill turn").toBeDefined();
  expect(answer!.params.root).toBe(path.join(info.root!, ".claude", "skills"));
  expect(answer!.params.names).toContain("cad");
  expect(answer!.params.names).toContain("hardcore-app-use");
  expect((answer!.params.cad as { path: string; text: string }).text).toContain("name: cad");
});

test("cadgen inside a session is the app's own", async () => {
  const sent = await run("claude-code", ["which"]);
  const created = sent.find((frame) => frame.kind === "session/new")!;
  const first = String(created.params.PATH ?? "").split(path.delimiter)[0]!;
  const shipped = [path.join(first, "cadgen"), path.join(first, "cadgen.cmd")].find((candidate) =>
    fs.existsSync(candidate),
  );
  if (!shipped) {
    // No CAD runtime resolved on this machine (no bundle, no checkout venv):
    // there is nothing for a session to find, which is not this test's fault.
    test.skip(true, "no CAD runtime on this machine");
    return;
  }
  const answer = sent.find((frame) => frame.kind === "which");
  expect(answer, "the fake agent's `command -v cadgen` turn").toBeDefined();
  expect(answer!.params.cadgen).toBe(shipped);
});

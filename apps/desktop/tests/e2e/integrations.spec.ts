import fs from "node:fs";
import path from "node:path";

import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import type { TextToCadApi } from "../../src/shared/ipc";
import { launch, mod, scratch } from "./launch";

/**
 * What the app gives an agent, on the wire (plan §8, as revised), and what an
 * agent can do with it — on one app.
 *
 *   - the skills root in every `session/new` (both spellings), the preamble
 *     only for an agent that will not read one, the workspace MCP server's two
 *     skills tools, and the app's own `cadgen` first on the session's PATH.
 *     Nothing is installed into any agent's own configuration;
 *   - the domain MCP servers `session/new` carries, each started by the agent
 *     with the environment the app gave it, operating the live app: browser
 *     tabs, documents with unsaved edits and revisions, drawings, PDFs and
 *     terminals, each checked on screen as well as in the reply.
 *
 * The fake agent appends a JSON line for every `session/new`, `session/load`
 * and prompt it is given (`FAKE_AGENT_RECORD`), and on `integration-proof`
 * runs the requested MCP calls itself (`tests/fake-agent/integration-proof.mjs`),
 * so what is asserted is the wire and the app, never a model.
 */

declare const window: { textToCad: TextToCadApi };

type Frame = { kind: string; params: Record<string, unknown> };
type ToolResult = { isError?: boolean; content: Array<{ type: string; text?: string; data?: string; mimeType?: string }> };

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let projectId: string;
let record: string;
let sessionId: string;
let counter = 0;
const errors: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  userData = scratch("integrations");
  project = path.join(userData, "integration-fixture");
  record = path.join(userData, "agent.jsonl");
  fs.mkdirSync(project);
  fs.writeFileSync(path.join(project, "notes.txt"), "disk original\n");
  fs.writeFileSync(path.join(project, "fixture.pdf"), pdfFixture());
  ({ app, page } = await launch({
    userData: path.join(userData, "profile"),
    env: { FAKE_AGENT_INTEGRATION_PROOF: "1", FAKE_AGENT_RECORD: record, CADGEN_DAEMON: "0" },
  }));
  page.on("pageerror", (error) => errors.push(error.message));
  await page.evaluate(() => window.textToCad.settings.set({ theme: "dark" }));
  projectId = (await page.evaluate((root) => window.textToCad.projects.addPath({ path: root }), project)).id;
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

test("the skills root is in session/new in both layouts, and the preamble only for an agent that ignores it", async () => {
  const info = await page.evaluate(() => window.textToCad.skills.info());
  const names = info.skills.map((skill) => skill.name);
  expect(names).toEqual(expect.arrayContaining(["cad", "cad-viewer", "documents", "pdf", "drawings", "terminals", "text-to-cad-browser"]));
  expect(names).not.toContain("text-to-cad-app-use");
  // One directory per app version, under the app's own user-data directory.
  expect(path.dirname(info.root!)).toBe(path.join(fs.realpathSync(path.join(userData, "profile")), "skills"));
  for (const layout of [path.join(".claude", "skills"), path.join(".agents", "skills")]) {
    for (const name of ["cad", "cad-viewer", "documents", "pdf", "drawings", "terminals", "text-to-cad-browser"]) {
      expect(fs.existsSync(path.join(info.root!, layout, name, "SKILL.md"))).toBe(true);
    }
  }

  // Claude Code loads the root itself: it is named on session/new, and its transcript is the
  // person's words. The workspace server's list_skills and read_skill reach the same root.
  const native = await run("claude-code", ["hello", "skills", "which"]);
  const created = native.find((frame) => frame.kind === "session/new")!;
  expect(created.params.additionalDirectories).toEqual([info.root]);
  expect(created.params._meta).toMatchObject({ additionalRoots: [info.root] });
  for (const prompt of native.filter((frame) => frame.kind === "prompt")) {
    expect(JSON.stringify(prompt.params.prompt)).not.toContain("Additional skills are at");
  }
  const skills = native.find((frame) => frame.kind === "skills")!;
  expect((skills.params.names as string[]).sort()).toEqual([...names].sort());
  expect(skills.params.cad).toEqual({ path: "cad/SKILL.md", text: fs.readFileSync(path.join(info.root!, ".claude", "skills", "cad", "SKILL.md"), "utf8") });
  // The app's own cadgen is first on the session's PATH, where `command -v` finds it.
  const first = String(created.params.PATH ?? "").split(path.delimiter)[0]!;
  const shipped = [path.join(first, "cadgen"), path.join(first, "cadgen.cmd")].find((candidate) => fs.existsSync(candidate));
  if (process.env.TEXT_TO_CAD_E2E_REQUIRE_CAD === "1") {
    expect(shipped, "CAD qualification requires the app's cadgen command in the session PATH").toBeDefined();
  }
  if (shipped) expect(native.find((frame) => frame.kind === "which")!.params.cadgen).toBe(shipped);

  // gemini-cli's `newSession` ignores additional directories: it is told once, in the first prompt.
  const told = (await run("gemini-cli", ["first", "second"])).filter((frame) => frame.kind === "prompt");
  expect(told).toHaveLength(2);
  expect(JSON.stringify(told[0]!.params.prompt)).toContain("Additional skills are at");
  expect(JSON.stringify(told[0]!.params.prompt)).toContain("- cad:");
  expect(JSON.stringify(told[1]!.params.prompt)).not.toContain("Additional skills are at");
});

test("a real ACP session starts isolated domain MCPs and operates the live app's resources", async () => {
  test.setTimeout(120_000);
  const session = await page.evaluate((id) => window.textToCad.sessions.create({ projectId: id, agentId: "claude-code", gitMode: "none", name: "Integration proof" }), projectId);
  sessionId = session.id;
  await page.locator(`[data-session-row="${sessionId}"]`).click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();

  const catalog = await proof({ operation: "catalog" }) as { catalog: Array<{ name: string; tools: string[] }> };
  expect(catalog.catalog.map((entry) => entry.name).sort()).toEqual(["browser", "cad", "documents", "drawings", "pdf", "terminals", "workspace"].map((name) => `text-to-cad-${name}`).sort());
  const tools = (name: string) => catalog.catalog.find((entry) => entry.name === `text-to-cad-${name}`)?.tools ?? [];
  expect(tools("documents")).toContain("edit_document");
  expect(tools("pdf")).not.toContain("edit_document");
  expect(tools("browser")).toContain("browser_snapshot");
  expect(tools("browser")).not.toContain("browser_connection");

  // Browser: a tab the tool opens is the explorer's tab. (The Playwright server is the slow one
  // to start, so this is one start; what the browser tools do is `browser-mcp.spec.ts`.)
  const [created, listed] = await batch("browser", [{ name: "browser_tabs", args: { action: "new" } }, { name: "browser_tabs", args: { action: "list" } }]);
  expect(created?.isError, JSON.stringify(created)).not.toBe(true);
  expect(JSON.stringify(listed)).toContain("about:blank");
  await expect(page.getByRole("tab", { name: /about:blank/ }).last()).toBeVisible();

  // Documents: the agent reads a person's unsaved draft, edits it against its revision, loses a
  // stale edit, and cannot close a dirty tab; the bridge refuses a caller without the right token.
  const opened = json<{ tabId: string }>(await tool("workspace", "open_file", { path: "notes.txt" }));
  await expect(page.locator(".monaco-editor").first()).toContainText("disk original");
  await page.locator(".monaco-editor .view-lines").first().click();
  // Monaco takes input through its own focused element (an EditContext, not a textarea).
  await expect(page.locator(".monaco-editor:focus-within")).toHaveCount(1);
  await page.keyboard.press(`${mod}+A`);
  // One input event, as a paste is: key-by-key typing into Monaco dropped a character under
  // CI load ("humn"), and what matters here is the draft, not the typing.
  await page.keyboard.insertText("human unsaved draft");
  await expect(page.getByLabel("Unsaved changes")).toBeVisible();
  let live = await readBound(opened.tabId);
  expect(live).toMatchObject({ content: "human unsaved draft", dirty: true });
  expect(fs.readFileSync(path.join(project, "notes.txt"), "utf8")).toBe("disk original\n");
  expect((await proof({ operation: "isolation", tabId: opened.tabId }) as { status: number }).status).toBe(403);
  const replaced = json<{ revision: string }>(await tool("documents", "edit_document", { tabId: opened.tabId, expectedRevision: live.revision, content: "agent reviewed draft" }));
  await expect(page.locator(".monaco-editor").first()).toContainText("agent reviewed draft");
  const [stale, refused] = [
    await tool("documents", "edit_document", { tabId: opened.tabId, expectedRevision: live.revision, content: "stale clobber" }),
    await tool("workspace", "close_tab", { tabId: opened.tabId }),
  ];
  expect(stale.isError).toBe(true);
  expect(stale.content[0]?.text).toMatch(/revision conflict/);
  expect(refused.isError).toBe(true);
  await expect(page.getByRole("tab", { name: /notes\.txt/ })).toBeVisible();

  // Drawings: an ephemeral tab the agent opens, reads and renames.
  const drawing = json<{ tabId: string }>(await tool("drawings", "open_drawing", { title: "MCP scratch" }));
  const [drawingState, renamed] = await batch("drawings", [
    { name: "drawing_state", args: { tabId: drawing.tabId } },
    { name: "rename_drawing", args: { tabId: drawing.tabId, title: "Assembly sketch" } },
  ]);
  expect(json(drawingState!)).toMatchObject({ elementCount: 0, ephemeral: true });
  json(renamed!);
  await expect(page.getByRole("tab", { name: /Assembly sketch/ })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Drawing name" })).toHaveValue("Assembly sketch");

  // Back to the document: hidden, it still holds the agent's text; shown, it binds again with a
  // new revision, and saves.
  expect(json(await tool("documents", "read_document", { tabId: opened.tabId }))).toMatchObject({ active: false, content: "agent reviewed draft", dirty: true });
  json(await tool("workspace", "show_tab", { tabId: opened.tabId }));
  live = await readBound(opened.tabId);
  expect(live.content).toBe("agent reviewed draft");
  expect(live.revision).not.toBe(replaced.revision);
  expect(json(await tool("documents", "save_document", { tabId: opened.tabId, expectedRevision: live.revision }))).toMatchObject({ status: "saved" });
  expect(fs.readFileSync(path.join(project, "notes.txt"), "utf8")).toBe("agent reviewed draft");

  // PDF: the text layer (CJK included) and a capture of the page on screen.
  const pdf = json<{ tabId: string }>(await tool("workspace", "open_file", { path: "fixture.pdf" }));
  await expect(page.getByText("Electron PDF integration", { exact: true })).toBeVisible();
  const [pdfState, pdfText, pdfCapture] = await batch("pdf", [
    { name: "pdf_state", args: { tabId: pdf.tabId } },
    { name: "read_pdf", args: { tabId: pdf.tabId } },
    { name: "capture_pdf", args: { tabId: pdf.tabId } },
  ]);
  expect(json(pdfState!)).toMatchObject({ page: 1, pageCount: 1, active: true });
  const text = json<{ pages: Array<{ text: string }> }>(pdfText!).pages[0]?.text;
  expect(text).toContain("Electron PDF integration");
  expect(text).toContain("日本");
  expect(pdfCapture!.isError).not.toBe(true);
  expect(pdfCapture!.content.find((block) => block.type === "image")?.mimeType).toBe("image/png");

  // Terminals: a pty the agent creates, writes to (against the sequence it read) and stops.
  const terminal = json<{ tabId: string }>(await tool("terminals", "create_terminal"));
  let output = json<Record<string, unknown>>(await tool("terminals", "read_terminal", { tabId: terminal.tabId }));
  await expect.poll(async () => {
    const write = await tool("terminals", "write_terminal", { tabId: terminal.tabId, data: 'printf "INTEGRATION_PTY_OK\\n"\n', expectedSequence: output.sequence, expectedInputRevision: output.inputRevision });
    if (write.isError) output = json(await tool("terminals", "read_terminal", { tabId: terminal.tabId }));
    return write.isError ? JSON.stringify(write) : "written";
  }).toBe("written");
  await expect.poll(async () => JSON.stringify(json(await tool("terminals", "read_terminal", { tabId: terminal.tabId })))).toContain("INTEGRATION_PTY_OK");
  json(await tool("terminals", "stop_terminal", { tabId: terminal.tabId }));
  const closedTabs = await batch("workspace", [
    { name: "close_tab", args: { tabId: terminal.tabId } },
    { name: "close_tab", args: { tabId: opened.tabId } },
  ]);
  closedTabs.forEach((result) => json(result));
  await expect(page.getByRole("tab", { name: /notes\.txt/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function frames(): Frame[] {
  if (!fs.existsSync(record)) return [];
  return fs.readFileSync(record, "utf8").trim().split("\n").filter(Boolean).map((line) => JSON.parse(line) as Frame);
}

/** One session with this agent, prompted in turn; the frames it produced. */
async function run(agentId: string, prompts: string[]): Promise<Frame[]> {
  const before = frames().length;
  const id = (await page.evaluate(({ projectId, agentId, cwd }) =>
    window.textToCad.sessions.create({ projectId, agentId, cwd, gitMode: "none" }), { projectId, agentId, cwd: project })).id;
  for (const text of prompts) {
    await page.evaluate(({ id, text }) => window.textToCad.sessions.prompt({ id, content: [{ type: "text", text }] }), { id, text });
  }
  return frames().slice(before);
}

/** One `integration-proof` turn: the fake agent runs the request and records the result. */
async function proof(request: Record<string, unknown>): Promise<unknown> {
  const id = String(++counter);
  const result = await page.evaluate(({ sessionId, text }) => window.textToCad.sessions.prompt({ id: sessionId, content: [{ type: "text", text }] }),
    { sessionId, text: `integration-proof ${JSON.stringify({ ...request, id })}` });
  expect(result.stopReason).toBe("end_turn");
  const entry = frames().find((frame) => frame.kind === "integration-proof" && frame.params.id === id);
  expect(entry, `Missing proof ${id}`).toBeDefined();
  return entry!.params.result;
}

async function tool(domain: string, name: string, args: Record<string, unknown> = {}): Promise<ToolResult> {
  return await proof({ domain, name, args }) as ToolResult;
}

/** Several calls through one server start: each `tool` call starts its domain's server anew. */
async function batch(domain: string, calls: Array<{ name: string; args: Record<string, unknown> }>): Promise<ToolResult[]> {
  return await proof({ operation: "batch", domain, calls }) as ToolResult[];
}

function json<T = Record<string, unknown>>(result: ToolResult): T {
  expect(result.isError, JSON.stringify(result)).not.toBe(true);
  return JSON.parse(result.content.find((item) => item.type === "text")?.text ?? "{}") as T;
}

/** A document tab answers once its editor has bound to the live document. */
async function readBound(tabId: string) {
  let result!: ToolResult;
  await expect.poll(async () => {
    result = await tool("documents", "read_document", { tabId });
    return result.isError ?? false;
  }).toBe(false);
  return json<{ content: string; revision: string; dirty: boolean; active: boolean }>(result);
}

function pdfFixture() {
  const stream = "BT /F1 16 Tf 20 100 Td (Electron PDF integration) Tj ET BT /F2 16 Tf 20 70 Td <65E5672C> Tj ET";
  const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R /F2 6 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiMin-W3 /Encoding /UniJIS-UTF16-H /DescendantFonts [7 0 R] >>",
    "<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiMin-W3 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 5 >> /FontDescriptor 8 0 R >>",
    "<< /Type /FontDescriptor /FontName /HeiseiMin-W3 /Flags 6 /FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 >>"];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => { offsets.push(pdf.length); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = pdf.length;
  return pdf + `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
}

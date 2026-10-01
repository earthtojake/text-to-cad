import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import type { TextToCadApi } from "../../src/shared/ipc";
import type { IntegrationCommand, IntegrationReply } from "../../src/shared/ipc/integrations";
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from "./cad-runtime";
import { launch, repoRoot, settleTerminal } from "./launch";
import { selectFixtureSession } from "./session-fixture";

/**
 * The CAD runtime's lifecycle in the desktop host, on ONE app and ONE compile.
 *
 * What only the host can prove, in the order a person meets it: selecting a
 * session warms the viewer and the build daemon before any file asks; a STEP
 * tab whose runtime cannot start says so in the interpreter's words and
 * recovers in place once the runtime is restored; the file then renders in
 * the desktop viewer and a reference from it reaches the prompt (and the
 * native clipboard); the live integration commands an agent's tools send drive
 * that mounted viewport; and quitting with all of it running ends every child
 * the app started.
 *
 * The viewer's own UI — display presets, the toolbar, the Features tree,
 * selection modes, animation — is `packages/ui`'s, tested there on every PR;
 * none of it is re-tested here.
 *
 * The first compile is the slow step of the suite, so it happens once: the
 * recovery test's retry is it, and everything after reuses the prepared model.
 */

declare const window: {
  textToCad: TextToCadApi;
  __cadCamera?: () => { position: number[]; target: number[]; projection: string } | null;
  localStorage: { getItem(key: string): string | null };
};
declare const document: { documentElement: { getAttribute(name: string): string | null } };

type CadLiveState = {
  active: boolean; loading: boolean; revision: string;
  resource: { kind: string; path?: string; revision?: string }; selection: unknown[];
  camera: { position: [number, number, number]; target: [number, number, number]; up: [number, number, number];
    projection?: "orthographic" | "perspective"; focalLength?: number } | null;
  display: { mode: string; camera?: { enabled?: boolean; projection?: string; focalLength?: number } }; renderMode: string;
};

const STEP = "part.step";
const stepBytes = fs.readFileSync(path.join(repoRoot, "tests/fixtures/cad/import-smoke.step"));
const revision = createHash("sha256").update(stepBytes).digest("hex");

let app: ElectronApplication;
let page: Page;
let lines: string[];
let userData: string;
let socketDir: string;
let project: string;
let session: Awaited<ReturnType<typeof selectFixtureSession>>;
let daemonPid: number | null = null;
const errors: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  userData = cadTestProfile("cad");
  // Python multiprocessing adds socket suffixes: the daemon's socket needs a short path.
  socketDir = fs.mkdtempSync("/tmp/hc-sock-");
  project = path.join(userData, "project");
  fs.mkdirSync(project);
  fs.writeFileSync(path.join(project, STEP), stepBytes);
  // The app resolves its own runtime (the bundle beside it, or the checkout's
  // `.venv`), so a developer's override is not inherited. Pre-warming is off
  // under test for every other spec; this one is about it. The daemon is on,
  // as it is for a person, on a private socket so the one this app starts is
  // provably its own.
  ({ app, page, lines } = await launch({
    userData,
    env: {
      ...cadRegistryEnvironment(userData),
      CAD_DESKTOP_PYTHON: undefined,
      TEXT_TO_CAD_PREWARM: "1",
      CADGEN_DAEMON: "1",
      CADGEN_CACHE_DIR: path.join(userData, "cad-cache"),
      CADGEN_DAEMON_STATE_DIR: path.join(userData, "cad-daemon"),
      ...(process.platform === "win32" ? {} : { CADGEN_DAEMON_SOCKET: path.join(socketDir, "d.sock") }),
    },
  }));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") console.error(`[CAD renderer] ${message.text()}`); });
  const runtime = await page.evaluate(() => window.textToCad.runtime.status());
  test.skip(!cadRuntimeReady(runtime), "CAD runtime required");
  await page.evaluate(() => window.textToCad.settings.set({ theme: "dark", reduceMotion: true }));
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1440, 900));
});

test.afterAll(async () => {
  // The quit test normally leaves nothing to close.
  await app?.close().catch(() => {});
  // The daemon the warm started is detached from the app by design: it is this spec's to stop.
  if (daemonPid !== null) {
    try { process.kill(daemonPid, "SIGTERM"); } catch { /* already gone */ }
  }
  const runtimeLog = path.join(userData, "cad-runtime.log");
  if (fs.existsSync(runtimeLog)) fs.copyFileSync(runtimeLog, test.info().outputPath("cad-runtime.log"));
  fs.rmSync(userData, { recursive: true, force: true });
  fs.rmSync(socketDir, { recursive: true, force: true });
});

test("selecting a session warms the viewer and the daemon before any file is opened", async () => {
  session = await selectFixtureSession(page, project);
  await expect.poll(() => lines.some((line) => /\[viewer\] (started|reused) http:\/\/127\.0\.0\.1:\d+ for /.test(line)), { timeout: 90_000 }).toBe(true);
  await expect.poll(() => lines.some((line) => /\[daemon\] warming .* \(pid \d+\)/.test(line)), { timeout: 30_000 }).toBe(true);
  daemonPid = Number(/\(pid (\d+)\)/.exec(lines.find((line) => /\[daemon\] warming .* \(pid \d+\)/.test(line))!)![1]);
  // "serving" in the runtime log is the daemon bound and answering, not merely spawned.
  const runtimeLog = path.join(userData, "cad-runtime.log");
  await expect.poll(() => (fs.existsSync(runtimeLog) ? fs.readFileSync(runtimeLog, "utf8") : ""), { timeout: 60_000 })
    .toMatch(/\[cadgen-daemon\] pid \d+ serving /);
  // Nothing asked for a viewer surface: the warm was the only reason for the launch.
  await expect(page.locator("[data-cad-surface]")).toHaveCount(0);
});

test("a STEP tab shows the runtime's own error, and Try again recovers the same tab once it is restored", async () => {
  test.setTimeout(150_000);
  // An override pointing nowhere gives every machine the same genuine runtime error, and
  // changing it stops the viewer the warm started.
  await page.evaluate(() => window.textToCad.settings.set({ cadPythonOverride: "/nowhere/python" }));
  expect((await page.evaluate(() => window.textToCad.runtime.status())).state).toBe("error");
  await page.getByRole("button", { name: "Toggle explorer", exact: true }).click();
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File" }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await page.getByLabel("Filter files").fill(STEP);
  await page.getByRole("option", { name: STEP, exact: false }).first().click();

  const failure = page.locator("[data-cad-failure=runtime-not-ready]");
  await expect(page.getByText("The CAD runtime did not start")).toBeVisible();
  await expect(failure).toContainText("/nowhere/python");
  await expect(page.getByRole("button", { name: "Runtime status" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("file-cad-failed.png"), animations: "disabled" });

  const tab = page.getByRole("tab", { name: /part\.step/ });
  const tabId = await tab.getAttribute("data-tab");
  await page.evaluate(() => window.textToCad.settings.set({ cadPythonOverride: null }));
  expect(cadRuntimeReady(await page.evaluate(() => window.textToCad.runtime.status()))).toBe(true);
  await page.getByRole("button", { name: "Try again" }).click();
  // The same tab, not a reopened one — and the first compile, in the daemon the warm started.
  await expect(tab).toHaveAttribute("data-tab", tabId!);
  await expect(page.locator("[data-tab-strip] [data-tab]")).toHaveCount(1);
  await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 120_000 });
});

test("a STEP renders in the desktop viewer, and its reference reaches the prompt and the clipboard", async () => {
  test.setTimeout(120_000);
  const previousClipboard = await app.evaluate(({ clipboard }) => clipboard.readText());
  try {
    const draft = page.getByPlaceholder("Do anything");
    await draft.fill("Keep this draft.");
    // The Features list is recognised in the packaged worker, under the desktop CSP: a lone
    // part listed as its features is that worker having run.
    const model = page.locator("[data-cad-tool-stack]").getByRole("list", { name: "Model", exact: true });
    const feature = model.getByRole("button", { name: /^Select Base (extrude|revolve)$/ }).first();
    await expect(feature).toBeVisible({ timeout: 90_000 });
    // The embedded surface renders from the appearance it is handed and never writes the document.
    expect(await page.evaluate(() => ({
      theme: document.documentElement.getAttribute("data-theme"),
      preference: document.documentElement.getAttribute("data-theme-preference"),
      stored: window.localStorage.getItem("cad-viewer:theme"),
    }))).toEqual({ theme: null, preference: null, stored: null });
    await page.screenshot({ path: test.info().outputPath("file-cad.png"), animations: "disabled" });

    // Copy Reference writes the native clipboard, in the CAD copy grammar: the file's prefix,
    // then the selector.
    await feature.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Copy Reference", exact: true }).click();
    await expect.poll(() => app.evaluate(({ clipboard }) => clipboard.readText())).toMatch(/^part\.step#o1\.f\d+(,o1\.f\d+)*$/);
    const copied = await app.evaluate(({ clipboard }) => clipboard.readText());

    // Add to prompt lands a chip beside the draft, and sends nothing.
    await feature.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Add to prompt", exact: true }).click();
    await expect(page.getByRole("menu")).toHaveCount(0);
    const chip = page.locator("[data-composer] [data-reference-chip]");
    await expect(chip).toHaveCount(1);
    await expect(chip).toHaveAttribute("data-file", STEP);
    const selector = (await chip.getAttribute("data-selector"))!;
    expect(copied.endsWith(selector)).toBe(true);
    await expect(draft).toContainText("Keep this draft.");

    // The camera attaches the viewport as an image.
    await page.getByRole("button", { name: "Take snapshot", exact: true }).click();
    await expect(page.locator("[data-composer]").getByText(/^part-view\.png$/)).toHaveCount(1);
    const unsent = await page.evaluate((id) => window.textToCad.sessions.state({ id }), session.id);
    expect(unsent?.state.turns ?? []).toHaveLength(0);

    // Sent: the text carries the chip's token, the snapshot goes as an image block.
    await draft.press("End");
    await page.keyboard.type(" what is this");
    await page.keyboard.press("Enter");
    await expect.poll(async () => {
      const state = await page.evaluate((id) => window.textToCad.sessions.state({ id }), session.id);
      return state?.state.turns.find((turn) => turn.role === "user")?.parts.map((part) => part.type).sort() ?? [];
    }).toEqual(["image", "text"]);
    const state = await page.evaluate((id) => window.textToCad.sessions.state({ id }), session.id);
    const parts = state!.state.turns.find((turn) => turn.role === "user")!.parts as Array<{ type: string; text?: string; mimeType?: string }>;
    expect(parts.find((part) => part.type === "text")?.text).toContain(`${STEP}#${selector}`);
    expect(parts.find((part) => part.type === "image")?.mimeType).toBe("image/png");
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
    expect(errors).toEqual([]);
  } finally {
    await app.evaluate(({ clipboard }, text) => clipboard.writeText(text), previousClipboard);
  }
});

test("live CAD commands observe and control the mounted viewport without prompt effects", async () => {
  // Only this window's replies are intercepted: the renderer's dispatch and the viewport
  // bindings are production code, and the reply is read here instead of by an MCP server.
  await app.evaluate(({ BrowserWindow }) => {
    const replies = new Map<string, unknown>();
    (globalThis as unknown as { cadLiveReplies: Map<string, unknown> }).cadLiveReplies = replies;
    BrowserWindow.getAllWindows()[0]!.webContents.ipc.handle("text-to-cad:integrations.reply", (_event, reply: { requestId: string }) => {
      replies.set(reply.requestId, reply);
    });
  });
  let sequence = 0;
  async function reply(kind: IntegrationCommand["kind"], tabId?: string, params?: Record<string, unknown>): Promise<IntegrationReply> {
    const requestId = `live-${++sequence}`;
    await app.evaluate(({ BrowserWindow }, command) => BrowserWindow.getAllWindows()[0]!.webContents.send("text-to-cad!integrations.command", command),
      { requestId, kind, sessionId: session.id, projectId: session.projectId, root: null, ...(tabId ? { tabId } : {}), ...(params ? { params } : {}), ...(kind === "open-file" ? { path: STEP } : {}) });
    let result: IntegrationReply | null = null;
    await expect.poll(async () => {
      result = await app.evaluate((_electron, id) => (globalThis as unknown as { cadLiveReplies: Map<string, IntegrationReply> }).cadLiveReplies.get(id) ?? null, requestId);
      return result !== null;
    }).toBe(true);
    return result!;
  }
  async function command(kind: IntegrationCommand["kind"], tabId?: string, params?: Record<string, unknown>) {
    const result = await reply(kind, tabId, params);
    expect(result.ok, result.error).toBe(true);
    return result.result;
  }

  // The file is already open: the command focuses its tab rather than opening a second.
  const { tabId } = await command("open-file") as { tabId: string };
  await expect(page.locator("[data-tab-strip] [data-tab]")).toHaveCount(1);
  let state!: CadLiveState;
  await expect.poll(async () => {
    const result = await reply("viewer-state", tabId);
    if (!result.ok) return false;
    state = result.result as CadLiveState;
    return state.active && !state.loading && state.camera !== null;
  }, { timeout: 60_000 }).toBe(true);
  expect(state.resource).toMatchObject({ kind: "workspace-file", path: STEP, revision });
  expect(state.revision).toBe(revision);

  const selected = await command("select-reference", tabId, { selector: STEP }) as CadLiveState;
  expect(selected.selection).toEqual([expect.objectContaining({ resource: expect.objectContaining({ path: STEP, revision }), target: { kind: "whole-resource" } })]);
  const captured = await command("capture-view", tabId) as CadLiveState & { base64: string; mimeType: string };
  expect(captured.selection).toEqual(selected.selection);
  expect(captured.mimeType).toBe("image/png");
  expect(Buffer.from(captured.base64, "base64").subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  expect((await command("cad-clear-selection", tabId) as CadLiveState).selection).toEqual([]);

  const initial = state.camera!;
  const moved = { ...initial, position: initial.position.map((value, index) => value + (index === 0 ? 5 : 0)) };
  await command("cad-camera", tabId, { camera: moved });
  const actual = await page.evaluate(() => window.__cadCamera?.());
  actual!.position.forEach((value, index) => expect(value).toBeCloseTo(moved.position[index]!, 5));
  expect((await reply("cad-camera", tabId, { camera: { ...initial, position: [1, 2] } })).ok).toBe(false);
  await command("cad-reset-camera", tabId);
  await expect.poll(async () => (await command("viewer-state", tabId) as CadLiveState).camera!.position[0]).not.toBeCloseTo(moved.position[0]!, 2);
  expect((await command("cad-render-mode", tabId, { mode: "render" }) as CadLiveState).renderMode).toBe("render");
  expect((await command("cad-render-mode", tabId, { mode: "inspect" }) as CadLiveState).display.mode).toBe("solid");

  // A tab that is not showing is not a viewport: commands that need one refuse, and show-tab
  // brings it back.
  await page.locator('[data-tab-strip] button[aria-label="New tab"][aria-haspopup="menu"]').click();
  await page.getByRole("menuitem", { name: /^Browser/ }).click();
  await expect.poll(async () => (await command("viewer-state", tabId) as CadLiveState).active).toBe(false);
  expect((await reply("cad-reset-camera", tabId)).ok).toBe(false);
  await command("show-tab", tabId);
  await expect.poll(async () => {
    const restored = await command("viewer-state", tabId) as CadLiveState;
    return restored.active && !restored.loading && restored.camera !== null;
  }).toBe(true);
  // None of it touched the prompt.
  await expect(page.locator("[data-composer] img, [data-composer] [data-reference-chip]")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the app quits with everything running and leaves no child behind", async () => {
  test.setTimeout(90_000);
  // A shell, a live adapter mid-turn (the fake's `slow` runs until stopped), the viewer and a
  // WebGL context are all up.
  await page.locator('[data-tab-strip] button[aria-label="New tab"][aria-haspopup="menu"]').click();
  await page.getByRole("menuitem", { name: /^Terminal/ }).click();
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await settleTerminal(page);
  const busy = await page.evaluate((projectId) => window.textToCad.sessions.create({ projectId, agentId: "codex", gitMode: "none" }), session.projectId);
  void page.evaluate((id) => window.textToCad.sessions.prompt({ id, content: [{ type: "text", text: "slow" }] }), busy.id).catch(() => {});
  await expect.poll(() => page.evaluate((id) => window.textToCad.sessions.get({ id }), busy.id).then((row) => row?.status)).toBe("running");

  const pid = app.process().pid!;
  // The warm daemon is detached by design and outlives the app; everything else is the app's.
  const tree = descendants(pid).filter((entry) => entry.pid !== daemonPid && !descendants(daemonPid ?? -1).some((child) => child.pid === entry.pid));
  expect(tree.length, "the app should have children to end").toBeGreaterThan(3);
  const exited = new Promise<void>((resolve) => app.process().once("exit", () => resolve()));
  // The real thing: the menu's Quit, Cmd+Q, the dock — all `app.quit()`. The connection drops
  // before the evaluate resolves; the exit is what counts.
  await app.evaluate(({ app: electronApp }) => electronApp.quit()).catch(() => {});
  // Gone by the kernel's word (`kill -0`), not Playwright's `exit`, which trails it by seconds.
  await expect.poll(() => alive(pid), { timeout: 30_000, intervals: [25] }).toBe(false);
  await expect.poll(() => tree.filter((entry) => alive(entry.pid)).map((entry) => ({ ...entry, current: processState(entry.pid) })), { timeout: 5_000 }).toEqual([]);
  await exited;
});

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function processState(pid: number): string {
  try {
    return execFileSync("ps", ["-o", "pid=,ppid=,pgid=,stat=,command=", "-p", String(pid)], { encoding: "utf8" }).trim().slice(0, 300);
  } catch {
    return "exited during inspection";
  }
}

/** Every descendant of `pid`, with a short name for the failure message. */
function descendants(pid: number): { pid: number; command: string }[] {
  if (pid < 0) return [];
  const out: { pid: number; command: string }[] = [];
  let children: string[];
  try {
    children = execFileSync("pgrep", ["-P", String(pid)], { encoding: "utf8" }).trim().split(/\s+/).filter(Boolean);
  } catch {
    children = [];
  }
  for (const child of children) {
    let command = "?";
    try {
      const full = execFileSync("ps", ["-o", "command=", "-p", child], { encoding: "utf8" }).trim();
      const type = /--type=([\w-]+)/.exec(full)?.[1];
      command = type ? `helper:${type}` : `${full.split(" ")[0]?.split("/").pop() ?? "?"} ${full.replace(/^\S+/, "").slice(0, 50)}`;
    } catch {
      /* gone already */
    }
    out.push({ pid: Number(child), command });
    out.push(...descendants(Number(child)));
  }
  return out;
}

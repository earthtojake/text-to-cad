import fs from "node:fs";
import http from "node:http";
import path from "node:path";

import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import type { TextToCadApi } from "../../src/shared/ipc";
import { launch, mod, repoRoot, scratch, settleTerminal } from "./launch";
import { selectFixtureSession } from "./session-fixture";

/**
 * The explorer's host side, on one app: what main reads, writes, watches and
 * runs for each kind of tab.
 *
 * The main project is the checkout the suite is running from — a real tree
 * with a `.gitignore`, `node_modules`, LFS pointers and a hundred thousand
 * files — because that is where the interesting failures are. Anything that
 * writes gets a scratch directory of its own.
 *
 * The file viewer's own chrome — the breadcrumb, the panel toggles, the CAD
 * surface — is `packages/ui`'s and tested there; a CAD file is `cad.spec.ts`.
 * The review is `git.spec.ts`.
 */

declare const window: {
  DataTransfer: new () => { items: { add(file: File): void } };
  DragEvent: new (type: string, init: Record<string, unknown>) => unknown;
  ClipboardEvent: new (type: string, init: Record<string, unknown>) => unknown;
  textToCad: TextToCadApi;
};

const MARKDOWN = "AGENTS.md";
const IMAGE = "apps/desktop/build/icon.png";
const STEP = "tests/fixtures/cad/import-smoke.step";

let app: ElectronApplication;
let page: Page;
let userData: string;
let docsDir: string;
let allFilesDir: string;
let browserDir: string;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  userData = scratch("explorer");
  // Copies of this repository's README and AGENTS: raw HTML, badge images, GFM tables and
  // hard-wrapped prose to save and diff, which is not something to do to the checkout.
  docsDir = scratch("docs");
  for (const name of ["README.md", "AGENTS.md"]) fs.copyFileSync(path.join(repoRoot, name), path.join(docsDir, name));
  allFilesDir = scratch("all-files");
  fs.mkdirSync(path.join(allFilesDir, "STEP"));
  fs.mkdirSync(path.join(allFilesDir, "node_modules"));
  fs.writeFileSync(path.join(allFilesDir, "node_modules", "existing.txt"), "test-owned dependency");
  fs.writeFileSync(path.join(allFilesDir, ".gitignore"), "/STEP/**\n!/STEP/**/\n*.unsupported\nnode_modules/\n");
  fs.writeFileSync(path.join(allFilesDir, ".DS_Store"), "test-owned metadata");
  fs.writeFileSync(path.join(allFilesDir, "output.unsupported"), Buffer.from([0, 1, 2]));
  fs.copyFileSync(path.join(repoRoot, STEP), path.join(allFilesDir, "STEP", "tom.step"));
  browserDir = scratch("browser");
  ({ app, page } = await launch({ userData }));
  await page.evaluate(() => window.textToCad.settings.set({ theme: "dark" }));
  await switchProject(repoRoot);
});

test.afterAll(async () => {
  await app?.close();
  for (const dir of [userData, docsDir, allFilesDir, browserDir]) fs.rmSync(dir, { recursive: true, force: true });
});

test("opens a markdown file as a preview, then as source", async () => {
  await newTab("File");
  await page.getByLabel("Filter files").fill(MARKDOWN);
  await page.getByRole("option", { name: MARKDOWN, exact: false }).first().click();
  // Rendered: the heading is an H1, not a line beginning with `#`.
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  await shoot("file-markdown-preview.png");
  await page.getByRole("button", { name: "View source" }).click();
  // Monaco, showing the raw text — the `#` the preview ate.
  await expect(page.locator(".view-lines").first()).toContainText("# AGENTS.md");
  await shoot("file-markdown-source.png");
  // Taking the tree back closes the source: back to the preview.
  await page.getByTestId("tree-toggle").click();
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
});

test("expands three levels of the tree, and keeps them across the remount a new tab is", async () => {
  await newTab("File");
  const folder = (relative: string) => page.locator(`[role="treeitem"][data-path="${relative}"]`);
  // Each level is a lazy `explorer.list`, and each used to be a click that shut the tree
  // instead of opening it once a file was open under any of them.
  await folder("apps").click();
  await folder("apps/web").click();
  await folder("apps/web/src").click();
  await expect(folder("apps/web/src/shared")).toBeVisible();
  await folder("apps/web/src/client").click();
  await page.locator(`[role="treeitem"][data-path="apps/web/src/client/unboundIdentifiers.test.js"]`).click();
  await expect(page.getByRole("tab", { name: /unboundIdentifiers\.test\.js/ })).toBeVisible();
  await expect(folder("apps/web/src/client")).toBeVisible();
  await folder("apps/web").click();
  await expect(folder("apps/web/src")).toHaveCount(0);
  await folder("apps/web").click();
  await expect(folder("apps/web/src/client")).toBeVisible();
  await shoot("file-tree-deep.png");
});

test("copies a relative and an absolute path from a row's context menu", async () => {
  const row = page.locator(`[role="treeitem"][data-path="apps/web/src/client/unboundIdentifiers.test.js"]`);
  await openContextMenu(row);
  // A file menu has no Copy reference: the paths say it, and a reference inside a file is the
  // viewer's to copy.
  await expect(page.getByRole("menu").getByRole("menuitem", { name: "Copy reference" })).toHaveCount(0);
  await expect(page.getByRole("menu").getByRole("menuitem", { name: "Move to Trash" })).toBeVisible();
  await pick("Copy relative path");
  await expect.poll(() => app.evaluate(({ clipboard }) => clipboard.readText())).toBe("apps/web/src/client/unboundIdentifiers.test.js");
  await openContextMenu(row);
  await pick("Copy path");
  await expect.poll(() => app.evaluate(({ clipboard }) => clipboard.readText()))
    .toBe(fs.realpathSync(path.join(repoRoot, "apps/web/src/client/unboundIdentifiers.test.js")));
  await page.getByRole("tab", { name: /unboundIdentifiers\.test\.js/ }).getByRole("button", { name: "Close unboundIdentifiers.test.js" }).click();
});

test("opens an image with its dimensions, and reveals it in the tree", async () => {
  await newTab("File");
  await openFromTree(IMAGE);
  await expect(page.locator(`img[alt="icon.png"]`)).toBeVisible();
  // The footer reports the real pixels.
  await expect(page.getByText(/\d+ × \d+ · /)).toBeVisible();
  await expect(page.getByRole("treeitem", { name: "icon.png" })).toHaveAttribute("aria-selected", "true");
  await shoot("file-image.png");
});

test("runs a command in a terminal tab, and replays its scrollback exactly once on reattach", async () => {
  await newTab("Terminal");
  await expect(page.locator(".xterm-screen")).toBeVisible();
  // A login shell reads the person's profile before it prompts; typing before then is echoed
  // twice. And the command and its output differ, or the echo alone would pass.
  await settleTerminal(page);
  await page.locator(".xterm-helper-textarea").click();
  await page.keyboard.type("echo text-to-cad-$((6 * 7))");
  await page.keyboard.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("text-to-cad-42", { timeout: 20_000 });
  await shoot("terminal.png");
  const seen = occurrences(await page.locator(".xterm-rows").innerText(), "text-to-cad-42");
  // Switching away unmounts the xterm and the pty keeps running; coming back writes the
  // buffered scrollback and subscribes to the live stream, and `terminal.data`'s sequence
  // number is what stops the two overlapping.
  await page.getByRole("tab").first().click();
  await expect(page.locator(".xterm-screen")).toHaveCount(0);
  await page.getByRole("tab", { name: /Terminal/ }).click();
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await settleTerminal(page);
  expect(occurrences(await page.locator(".xterm-rows").innerText(), "text-to-cad-42")).toBe(seen);
});

test("persists the strip across a reload", async () => {
  const before = await page.getByRole("tab").count();
  expect(before).toBeGreaterThan(1);
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  // A reload starts on the new-session screen; the strip is the owning session's.
  await switchProject(repoRoot);
  await expect(page.getByRole("tab")).toHaveCount(before);
});

test("edits a markdown file in place and saves only the lines it changed", async () => {
  await switchProject(docsDir);
  await newTab("File");
  await page.getByLabel("Filter files").fill("AGENTS.md");
  await page.getByRole("option", { name: "AGENTS.md", exact: false }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  // Scoped to the explorer: the composer is a ProseMirror editor as well.
  await page.getByTestId("explorer").locator(".ProseMirror p").first().click();
  await page.keyboard.type("Edited in the app. ");
  await expect(page.getByLabel("Unsaved changes")).toBeVisible();
  await page.keyboard.press(`${mod}+s`);
  await expect(page.getByLabel("Unsaved changes")).toHaveCount(0);
  // The edited paragraph is re-printed; every other line of the document is exactly the line it was.
  const before = fs.readFileSync(path.join(repoRoot, "AGENTS.md"), "utf8");
  const after = fs.readFileSync(path.join(docsDir, "AGENTS.md"), "utf8");
  expect(after.replace(/\s+/g, " ")).toContain("Edited in the app.");
  const editedBlock = before.split("\n\n")[1]!;
  const untouched = before.split("\n").filter((line) => line.trim() !== "" && !editedBlock.includes(line));
  expect(untouched.length).toBeGreaterThan(100);
  for (const line of untouched) expect(after, `a line nobody edited was rewritten: ${line}`).toContain(line);
});

test("makes a folder from the tree's menu, renames it, and moves it to the trash", async () => {
  const tree = page.getByTestId("explorer").getByRole("tree");
  const folder = (name: string) => page.locator(`[role="treeitem"][data-path="${name}"]`);
  await page.getByLabel("Filter files").fill("");
  await expect(folder("README.md")).toBeVisible();
  // The empty space under the rows is the root: New folder, typed in place.
  await openContextMenu(tree, { x: 40, y: 200 });
  await pick("New folder");
  await expect(page.getByLabel("New folder name")).toBeFocused();
  await page.getByLabel("New folder name").fill("parts");
  await page.keyboard.press("Enter");
  await expect(folder("parts")).toBeVisible();
  expect(fs.statSync(path.join(docsDir, "parts")).isDirectory()).toBe(true);
  await openContextMenu(folder("parts"));
  await pick("Rename");
  await expect(page.getByLabel("Rename parts")).toBeFocused();
  await page.getByLabel("Rename parts").fill("assemblies");
  await page.keyboard.press("Enter");
  await expect(folder("assemblies")).toBeVisible();
  expect(fs.existsSync(path.join(docsDir, "parts"))).toBe(false);
  // A file inside it, from the folder's own menu, opens once it is made.
  await openContextMenu(folder("assemblies"));
  await pick("New file");
  await page.getByLabel("New file name").fill("notes.md");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: /notes\.md/ })).toBeVisible();
  expect(fs.readFileSync(path.join(docsDir, "assemblies", "notes.md"), "utf8")).toBe("");
  // F2 renames the cursor row, and Escape leaves it alone.
  await folder("assemblies/notes.md").click();
  await tree.focus();
  await page.keyboard.press("F2");
  await expect(page.getByLabel("Rename notes.md")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Rename notes.md")).toHaveCount(0);
  // Move to Trash: no dialog, the row goes, and so does the tab that showed the file.
  await openContextMenu(folder("assemblies"));
  await pick("Move to Trash");
  await expect(folder("assemblies")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /notes\.md/ })).toHaveCount(0);
  await expect.poll(() => fs.existsSync(path.join(docsDir, "assemblies"))).toBe(false);
});

test("lists every file, refreshes ignored folders and opens unknown types as Not supported", async () => {
  await switchProject(allFilesDir);
  await newTab("File");
  const entry = (file: string) => page.locator(`[role="treeitem"][data-path="${file}"]`);
  await expect(entry(".DS_Store")).toBeVisible();
  await expect(entry("output.unsupported")).toBeVisible();
  await entry("STEP").click();
  await expect(entry("STEP/tom.step")).toBeVisible();
  // Both recursive output watching and direct dependency-directory watching refresh rows.
  fs.copyFileSync(path.join(repoRoot, STEP), path.join(allFilesDir, "STEP", "new.step"));
  await expect(entry("STEP/new.step")).toBeVisible();
  await entry("node_modules").click();
  await expect(entry("node_modules/existing.txt")).toBeVisible();
  fs.writeFileSync(path.join(allFilesDir, "node_modules", "new.unsupported"), Buffer.from([0, 3, 4]));
  await expect(entry("node_modules/new.unsupported")).toBeVisible();
  fs.unlinkSync(path.join(allFilesDir, "node_modules", "new.unsupported"));
  await expect(entry("node_modules/new.unsupported")).toHaveCount(0);
  await page.getByLabel("Filter files").fill("output.unsupported");
  await page.getByRole("option", { name: "output.unsupported", exact: false }).click();
  await expect(page.getByText("Not supported", { exact: true })).toBeVisible();
});

/**
 * A drawing tab: real canvas ink becomes a PNG in the composer without sending anything, the
 * drawing never touches the disk or opens a dialog, and it is not one of the tabs a reload
 * restores. The editor's own controls are `packages/ui`'s.
 */
test("a drawing attaches a PNG without sending, writes nothing, and is not restored", async () => {
  const sketchDir = path.join(allFilesDir, "sketch");
  fs.mkdirSync(sketchDir);
  const session = await switchProject(sketchDir);
  const externalRequests: string[] = [];
  let downloads = 0;
  const onDownload = () => { downloads += 1; };
  page.on("download", onDownload);
  // Offline: the editor, its fonts and its PNG export are all local.
  await page.route(/^https?:\/\//, (route) => {
    const hostname = new URL(route.request().url()).hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") return route.continue();
    externalRequests.push(route.request().url());
    return route.abort();
  });
  await app.evaluate(({ dialog }) => {
    dialog.showSaveDialog = async () => { throw new Error("Drawing attempted to open a save dialog"); };
    dialog.showOpenDialog = async () => { throw new Error("Drawing attempted to open a load dialog"); };
  });
  try {
    await newTab("Drawing");
    const surface = page.locator("[data-drawing-tab]");
    const addToPrompt = surface.getByRole("button", { name: "Add to prompt", exact: true });
    await expect(addToPrompt).toBeDisabled();
    await surface.getByRole("textbox", { name: "Drawing name" }).fill("Bracket concept");
    await surface.getByRole("textbox", { name: "Drawing name" }).press("Enter");
    const canvas = surface.locator(".text-to-cad-drawing-editor canvas.excalidraw__canvas.interactive");
    await expect(canvas).toBeVisible();
    const box = (await canvas.boundingBox())!;
    const tools = surface.getByRole("group", { name: "Drawing tools" });
    await tools.getByRole("button", { name: "Rectangle", exact: true }).click();
    const x = box.x + box.width * 0.55;
    const y = box.y + box.height * 0.45;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 90, y + 65, { steps: 12 });
    await page.mouse.up();
    await expect(addToPrompt).toBeEnabled();

    const composer = page.getByPlaceholder("Do anything");
    await composer.fill("Keep this existing prompt text.");
    await addToPrompt.click();
    const png = page.locator('[data-composer] img[alt="Bracket_concept.png"]').first();
    // The CSP excludes blob URLs from fetch, so decoding is checked through the image itself.
    await expect.poll(() => png.evaluate((image) => {
      const decoded = image as unknown as { complete: boolean; naturalWidth: number; naturalHeight: number };
      return decoded.complete && decoded.naturalWidth > 100 && decoded.naturalHeight > 100;
    })).toBe(true);
    await expect(composer).toContainText("Keep this existing prompt text.");
    await expect(composer).toContainText("Drawing: Bracket concept.");
    await expect(page.locator("[data-turn][data-role=user]")).toHaveCount(0);
    await shoot("drawing-with-prompt.png");

    // The editor's own save, open and export shortcuts reach nothing, and a scene file cannot
    // load itself through a drop or a paste.
    await canvas.click({ position: { x: box.width * 0.8, y: box.height * 0.6 } });
    for (const keys of ["Shift+S", "O", "Shift+E"]) await page.keyboard.press(`${mod}+${keys}`);
    await surface.locator(".text-to-cad-drawing-editor").evaluate((element) => {
      const file = new File([JSON.stringify({ type: "excalidraw", version: 2, elements: [] })], "scene.excalidraw", { type: "application/json" });
      const data = new window.DataTransfer();
      data.items.add(file);
      element.dispatchEvent(new window.DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: data }) as Parameters<typeof element.dispatchEvent>[0]);
      element.dispatchEvent(new window.ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: data }) as Parameters<typeof element.dispatchEvent>[0]);
    });
    await expect(surface.getByRole("dialog")).toHaveCount(0);
    await expect(addToPrompt).toBeEnabled();
    expect(fs.readdirSync(sketchDir)).toEqual([]);

    // Ephemeral: the tabs main keeps for this session do not include it, so a reload brings
    // back the strip without it.
    await newTab("Browser");
    await expect.poll(async () => (await page.evaluate((id) => window.textToCad.explorer.loadTabs({ sessionId: id }), session.id))
      .map((tab) => tab.kind)).toEqual(["browser"]);
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await switchProject(sketchDir);
    await expect(page.getByRole("tab", { name: /^New tab/ })).toBeVisible();
    await expect(page.locator("[data-drawing-tab]")).toHaveCount(0);
    expect(downloads).toBe(0);
    expect(externalRequests).toEqual([]);
  } finally {
    page.off("download", onDownload);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
});

/**
 * A browser tab is a native page main owns. The explorer and the app tools reach the same
 * one through IPC; it survives tab and session switches, belongs to its session alone, puts a
 * screenshot and a selection in the prompt, and is gone when its tab closes.
 */
test("a browser tab's native page is shared by the explorer and the app tools, per session", async () => {
  const server = http.createServer((_request, response) => {
    response.setHeader("Content-Type", "text/html");
    response.end('<!doctype html><title>Persistent browser</title><label>Name <input id="name"></label><p>Native page fixture</p>');
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${(server.address() as { port: number }).port}/`;
  try {
    const project = await page.evaluate((directory) => window.textToCad.projects.addPath({ path: directory }), browserDir);
    const [sessionA, sessionB] = await page.evaluate(async (projectId) => [
      (await window.textToCad.sessions.create({ projectId, agentId: "claude-code", gitMode: "checkout" })).id,
      (await window.textToCad.sessions.create({ projectId, agentId: "claude-code", gitMode: "checkout" })).id,
    ], project.id);
    await page.locator(`[data-session-row="${sessionA}"]`).click();
    await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
    await page.getByRole("button", { name: "Toggle explorer" }).click();
    await newTab("Browser");
    await page.getByRole("textbox", { name: "Address" }).fill(origin);
    await page.getByRole("textbox", { name: "Address" }).press("Enter");
    const tabId = (await page.locator("[data-browser-target]").getAttribute("data-browser-target"))!;
    const scope = { sessionId: sessionA!, projectId: project.id, root: null, tabId };
    const metadata = () => page.evaluate((target) => window.textToCad.browser.metadata(target), scope);
    await expect.poll(async () => (await metadata()).url).toBe(origin);
    await expect.poll(async () => (await metadata()).visible).toBe(true);
    const nativeId = await app.evaluate(async ({ webContents }, url) => {
      const target = webContents.getAllWebContents().find((contents) => contents.getURL() === url)!;
      await target.executeJavaScript("document.getElementById('name').focus()");
      return target.id;
    }, origin);
    await page.evaluate((target) => window.textToCad.browser.input({ ...target, input: { action: "type", text: "Still here" } }), scope);
    const fieldValue = () => app.evaluate(async ({ webContents }, id) => webContents.fromId(id)!.executeJavaScript("document.getElementById('name').value"), nativeId);
    await expect.poll(fieldValue).toBe("Still here");
    // Hidden behind another tab, and kept.
    await newTab("File");
    await expect.poll(async () => (await metadata()).visible).toBe(false);
    await page.getByRole("tab", { name: /127\.0\.0\.1/ }).click();
    await expect.poll(fieldValue).toBe("Still here");
    // Another session in the same directory sees none of it.
    await page.locator(`[data-session-row="${sessionB}"]`).click();
    await expect(page.getByRole("tab", { name: /127\.0\.0\.1/ })).toHaveCount(0);
    await expect.poll(async () => (await metadata()).visible).toBe(false);
    await expect(page.evaluate((target) => window.textToCad.browser.metadata(target), { ...scope, sessionId: sessionB! })).rejects.toThrow();
    await page.locator(`[data-session-row="${sessionA}"]`).click();
    await expect(page.locator(`[data-browser-target="${tabId}"]`)).toBeVisible();
    await expect.poll(fieldValue).toBe("Still here");

    // A screenshot and a selection of the page go to the prompt; nothing is sent.
    const composer = page.getByPlaceholder("Do anything");
    await composer.fill("Keep this draft");
    await page.getByRole("button", { name: "Add page screenshot to prompt" }).click();
    const image = page.locator('[data-composer] img[alt="browser-page.png"]').first();
    await expect.poll(() => image.evaluate((element) => (element as unknown as { naturalWidth: number }).naturalWidth)).toBeGreaterThan(200);
    await app.evaluate(async ({ webContents }, id) => {
      await webContents.fromId(id)!.executeJavaScript("{const r=document.createRange();r.selectNodeContents(document.querySelector('p'));const s=window.getSelection();s.removeAllRanges();s.addRange(r);}");
    }, nativeId);
    await page.getByRole("button", { name: "Add selected text to prompt" }).click();
    await expect(page.locator("[data-composer]").getByText("browser-selection.txt")).toBeVisible();
    await expect(composer).toContainText("Keep this draft");
    await expect(page.locator("[data-turn][data-role=user]")).toHaveCount(0);
    await shoot("browser-app-shell.png");
    // Closing the tab ends the native page.
    await page.getByRole("tab", { name: /127\.0\.0\.1/ }).getByRole("button", { name: /Close/ }).click();
    await expect.poll(() => app.evaluate(({ webContents }, id) => !!webContents.fromId(id), nativeId)).toBe(false);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/** Select the fixture's session for `directory` (made on first use) and open its explorer. */
async function switchProject(directory: string) {
  const session = await selectFixtureSession(page, directory);
  if (!(await page.getByTestId("explorer").isVisible())) {
    await page.getByRole("button", { name: "Toggle explorer" }).click();
  }
  await expect(page.getByTestId("explorer")).toBeVisible();
  return session;
}

/** Open a path through the tree's filter — the way a person would. */
async function openFromTree(target: string) {
  const filter = page.getByLabel("Filter files");
  await filter.fill(target);
  await page.getByRole("option", { name: target, exact: false }).first().click();
  await expect(page.getByRole("tablist", { name: "Explorer tabs" }).locator('[role="tab"][aria-selected="true"]')).toHaveAttribute("title", target);
  if (await filter.isVisible()) await filter.fill("");
}

/**
 * macOS opens a context menu on right-button down, and during its entry animation a clamped
 * popup can overlap the pointer: Radix reads a release over an item as drag-selection
 * (including Move to Trash). Let the popup's animations finish before the release.
 */
async function openContextMenu(target: Locator, position?: { x: number; y: number }) {
  if (process.platform !== "darwin") {
    await target.click({ button: "right", ...(position ? { position } : {}) });
  } else {
    await target.scrollIntoViewIfNeeded();
    const box = (await target.boundingBox())!;
    await page.mouse.move(box.x + (position?.x ?? box.width / 2), box.y + (position?.y ?? box.height / 2));
    await page.mouse.down({ button: "right" });
    try {
      const menu = page.getByRole("menu");
      await expect(menu).toBeVisible();
      await menu.evaluate((node) => Promise.all(node.getAnimations({ subtree: true })
        .map((animation: { finished: Promise<unknown> }) => animation.finished.catch(() => {}))));
    } finally {
      await page.mouse.up({ button: "right" });
    }
  }
  await expect(page.getByRole("menu")).toBeVisible();
}

/** Pick an item from the open menu, and wait for the menu to be gone (its exit animation included). */
async function pick(item: string) {
  await page.getByRole("menu").getByRole("menuitem", { name: item }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

/** The explorer pane, not the window: the rest of the window belongs to other specs. */
async function shoot(name: string) {
  await page.getByTestId("explorer").screenshot({ path: test.info().outputPath(name), animations: "disabled" });
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/** `+` is a menu of the tab kinds; a closing Radix menu can swallow the next click, so wait it out. */
async function newTab(label: "File" | "Browser" | "Terminal" | "Drawing") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  if (label === "File") await expect(page.getByText("No file open", { exact: true })).toBeVisible();
}

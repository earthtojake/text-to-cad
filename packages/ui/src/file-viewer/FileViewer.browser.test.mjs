import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import { build } from "esbuild";
import { chromium } from "playwright";

let server, browser, temporary, page;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), "text-to-cad-file-viewer-browser-"));
  await build({ entryPoints: [fileURLToPath(new URL("./harness/index.tsx", import.meta.url))], outfile: join(temporary, "harness.js"), bundle: true, format: "esm", platform: "browser", jsx: "automatic", loader: { ".svg": "dataurl" } });
  const bundle = await readFile(join(temporary, "harness.js"));
  // The package's own stylesheet, so the chrome is laid out as a host lays it out.
  const styles = await readFile(fileURLToPath(new URL("../../dist/styles.css", import.meta.url)));
  server = createServer((request, response) => {
    if (request.url === "/harness.js") { response.setHeader("Content-Type", "text/javascript"); response.end(bundle); }
    else if (request.url === "/styles.css") { response.setHeader("Content-Type", "text/css"); response.end(styles); }
    else { response.setHeader("Content-Type", "text/html"); response.end('<!doctype html><html><head><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage();
  page.setDefaultTimeout(10_000);
  page.on("pageerror", (error) => console.error("Browser harness error:", error.message));
});
after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); if (temporary) await rm(temporary, { recursive: true, force: true }); });
async function reset() {
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.getByTestId("primary").getByRole("textbox", { name: "Document", exact: true }).waitFor();
}
const document = () => page.getByTestId("primary").getByRole("textbox", { name: "Document", exact: true });
async function waitValue(value) { await page.waitForFunction((expected) => document.querySelector('[data-testid="primary"] textarea')?.value === expected, value); }

test("injected renderer edits, saves and distinguishes conflicts from failures", async () => {
  await reset();
  await document().fill("local edit");
  await page.getByLabel("Unsaved changes").waitFor({ state: "attached" });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByLabel("Unsaved changes").waitFor({ state: "detached" });
  assert.equal(await page.evaluate(() => window.harness.a.files.get("notes.txt").content), "local edit");
  await document().fill("keep my edit");
  await page.evaluate(() => window.harness.a.change("notes.txt", "external edit", false));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("button", { name: "Reload", exact: true }).waitFor();
  assert.equal(await document().inputValue(), "keep my edit");
  await page.getByRole("button", { name: "Reload", exact: true }).click();
  await waitValue("external edit");
  await document().fill("cannot save");
  await page.evaluate(() => window.harness.a.fail(true));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("alert").waitFor();
  assert.match(await page.getByRole("alert").textContent(), /disk is full/);
  assert.equal(await page.getByRole("button", { name: "Reload", exact: true }).count(), 0);
});
test("watchers reload clean documents while dirty documents retain their draft", async () => {
  await reset();
  await page.evaluate(() => window.harness.a.change("notes.txt", "fresh disk"));
  await waitValue("fresh disk");
  await document().fill("draft survives");
  await page.evaluate(() => window.harness.a.change("notes.txt", "new disk"));
  await page.getByRole("button", { name: "Keep mine" }).waitFor();
  assert.equal(await document().inputValue(), "draft survives");
  await page.getByRole("button", { name: "Keep mine" }).click();
  assert.equal(await document().inputValue(), "draft survives");
  // The tree is not where a document opens: it is opened to watch it take the new file.
  await page.getByTestId("tree-toggle").click();
  await page.evaluate(() => window.harness.a.add("added.txt"));
  await page.getByRole("treeitem", { name: "added.txt", exact: true }).waitFor();
});
test("typing during save and late writes after a root switch cannot replace another draft", async () => {
  await reset();
  await document().fill("first draft");
  await page.evaluate(() => window.harness.a.hold(true));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await document().fill("newer draft");
  await page.evaluate(() => window.harness.a.releaseWrites());
  await page.waitForFunction(() => window.harness.a.files.get("notes.txt").content === "first draft");
  assert.equal(await document().inputValue(), "newer draft");
  assert.equal(await page.getByLabel("Unsaved changes").count(), 1);
  await page.evaluate(() => window.harness.a.hold(true));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.evaluate(() => window.harness.setRoot("root-b"));
  await waitValue("root-b original");
  await document().fill("root-b draft");
  await page.evaluate(() => window.harness.a.releaseWrites());
  await page.waitForFunction(() => window.harness.a.files.get("notes.txt").content === "newer draft");
  assert.equal(await document().inputValue(), "root-b draft");
});
test("panel exclusivity, capability menus, rename and create use the shared chrome", async () => {
  await reset();
  // A document opens with no panel: its renderer's Details does not claim the default, and
  // the tree is not where a file opens — only where there is no file to show.
  assert.equal(await page.getByRole("tree").count(), 0);
  assert.equal(await page.getByText("Injected panel").count(), 0);
  assert.equal(await page.getByTestId("tree-toggle").getAttribute("aria-pressed"), "false");
  assert.equal(await page.getByTestId("tree-toggle").getAttribute("aria-label"), "Show files");
  await page.getByRole("button", { name: "Details", exact: true }).click();
  await page.getByText("Injected panel").waitFor();
  assert.equal(await page.getByRole("tree").count(), 0);
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  assert.equal(await page.getByText("Injected panel").count(), 0);
  // The navbar's ⋯ is the explorer's menu for the open file: what the host can do, and no more.
  // A press on the navbar is one outside the explorer, which goes.
  await page.getByTestId("file-actions").click();
  assert.equal(await page.getByRole("tree").count(), 0, "a press on the navbar puts the explorer away");
  assert.equal(await page.getByRole("menuitem", { name: /Reveal|Open with|Move to trash/ }).count(), 0);
  await page.getByRole("menuitem", { name: /^Rename/ }).click();
  await page.getByRole("textbox", { name: "Rename file", exact: true }).fill("renamed.txt");
  await page.getByRole("textbox", { name: "Rename file", exact: true }).press("Enter");
  await page.locator('[data-file-name]', { hasText: "renamed.txt" }).waitFor();
  // The tab follows the file to its new name through the host.
  const renamed = await page.evaluate(() => window.harness.opened.at(-1));
  assert.deepEqual([renamed.path, renamed.options.target], ["renamed.txt", "current"]);
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  await page.getByRole("tree").dispatchEvent("contextmenu", { button: 2 });
  await page.getByRole("menuitem", { name: /New file/ }).click();
  await page.getByRole("textbox", { name: "New file name", exact: true }).fill("created.txt");
  await page.getByRole("textbox", { name: "New file name", exact: true }).press("Enter");
  await page.locator('[data-file-name]', { hasText: "created.txt" }).waitFor();
  // Made in the tree, the file is opened the way a pick there opens one: with the tree.
  assert.deepEqual(await page.evaluate(() => window.harness.opened.at(-1)), { path: "created.txt", options: { target: "new", panel: "tree" } });
  assert.equal(await page.getByRole("tree").count(), 1);
});
test("an empty tab asks for a file with the explorer shut, and a pick in the explorer opens the file with the tree", async () => {
  // With no file to show, the navbar asks for one; the explorer opens when the person asks.
  await reset();
  await page.evaluate(() => window.harness.open(null));
  await page.getByText("Select file", { exact: true }).waitFor();
  assert.equal(await page.getByRole("tree").count(), 0);
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  assert.equal(await page.getByTestId("tree-toggle").getAttribute("aria-pressed"), "true");

  // A pick in the tree asks the host for the file WITH the tree, so a person walks it file by file.
  await page.locator('[role="treeitem"][data-path="next.txt"]').click();
  await waitValue("root-a next");
  assert.deepEqual(await page.evaluate(() => window.harness.opened.at(-1)), { path: "next.txt", options: { target: "new", panel: "tree" } });
  assert.equal(await page.getByRole("tree").count(), 1, "the tree is still open on the file");
  await page.locator('[role="treeitem"][data-path="notes.txt"]').click();
  await waitValue("root-a original");
  assert.equal(await page.getByRole("tree").count(), 1, "and on the next one");
  assert.equal(await page.evaluate(() => window.harness.state.panel), "tree");

  // A file in folders nobody has opened is revealed as the tab reaches it: the tree opens them,
  // and they stay open — nothing the move writes lands over them.
  await page.evaluate(() => { window.harness.a.add("nested/deep/file.txt"); window.harness.open("nested/deep/file.txt"); });
  await waitValue("added");
  const revealed = page.locator('[role="treeitem"][data-path="nested/deep/file.txt"]');
  await revealed.waitFor();
  assert.equal(await revealed.getAttribute("aria-selected"), "true");
  await page.waitForTimeout(200);
  assert.deepEqual(await page.evaluate(() => window.harness.state.expandedDirectories), ["", "nested", "nested/deep"]);
  assert.equal(await revealed.isVisible(), true, "and the folders it was revealed in are still open");
});
test("the explorer's width stays bounded", async () => {
  await reset();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  await page.evaluate(() => window.harness.width(99999));
  // The width is bounded at the explorer's maximum. (The store write renders on React's
  // schedule, so the handle is read once it has.)
  const handle = page.getByRole("separator", { name: "Resize files panel" });
  await page.waitForFunction(() => document.querySelector('[role="separator"][aria-label="Resize files panel"]')?.getAttribute("aria-valuenow") !== "300");
  assert.equal(await handle.getAttribute("aria-valuenow"), await handle.getAttribute("aria-valuemax"));
});
test("root changes, multiple instances, cancelled loads and readonly documents remain isolated", async () => {
  await reset();
  await document().fill("root-a draft");
  await page.evaluate(() => window.harness.setRoot("root-b"));
  await waitValue("root-b original");
  assert.equal(await page.getByLabel("Unsaved changes").count(), 0);
  await page.evaluate(() => { window.harness.setRoot("root-a"); window.harness.second(true); });
  await waitValue("root-a original");
  await document().fill("a only");
  assert.equal(await page.getByTestId("secondary").getByRole("textbox", { name: "Document", exact: true }).inputValue(), "root-b original");
  await page.evaluate(() => window.harness.second(false));
  await page.evaluate(() => window.harness.open("slow.txt"));
  await page.getByRole("status").filter({ hasText: "Opening" }).waitFor();
  await page.evaluate(() => window.harness.open("next.txt"));
  await waitValue("root-a next");
  assert.ok(await page.evaluate(() => window.harness.events.includes("root-a:aborted")));
  assert.ok(await page.evaluate(() => window.harness.events.includes("root-b:notes.txt:disposed")));
  await page.evaluate(() => window.harness.open("readonly.txt"));
  await waitValue("truncated");
  assert.equal(await document().getAttribute("readonly"), "");
  assert.equal(await page.getByRole("button", { name: "Save", exact: true }).isDisabled(), true);
});
test("a former renderer cannot change the new root's panels or state", async () => {
  await reset();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  await page.evaluate(() => window.harness.setRoot("root-b"));
  await waitValue("root-b original");
  await page.evaluate(() => {
    const stale = window.harness.rendererCallbacks.get("root-a");
    stale.onPanelOpen("details"); stale.onStateChange({ from: "old root" });
  });
  await page.getByTestId("tree-toggle").waitFor();
  assert.equal(await page.getByTestId("tree-toggle").isDisabled(), false);
  assert.equal(await page.getByRole("tree").count(), 1);
  assert.equal(await page.getByText("Injected panel").count(), 0);
  assert.equal(await page.evaluate(() => window.harness.state.renderers), undefined);
});

test("navbar actions belong to the active file generation and ignore retired registrations", async () => {
  await reset();
  await page.evaluate(() => {
    const current = window.harness.rendererCallbacks.get('root-a');
    window.retiredNavbar = current.onNavigationActionsChange;
    current.onNavigationActionsChange([{ id: 'fixture', label: 'Inspect notes', icon: 'span',
      onInvoke: () => window.harness.events.push('notes-action') }]);
  });
  await page.getByRole('button', { name: 'Inspect notes', exact: true }).click();
  assert.ok(await page.evaluate(() => window.harness.events.includes('notes-action')));
  // A hint shorter than the accessible name is the action's own field, not a special case in the navbar.
  await page.evaluate(() => window.harness.rendererCallbacks.get('root-a').onNavigationActionsChange([
    { id: 'snapshot', label: 'Take snapshot', hint: 'Snapshot', icon: 'span', onInvoke() {} }]));
  await page.mouse.move(0, 0);
  await page.getByRole('button', { name: 'Take snapshot', exact: true }).hover();
  assert.equal(await page.getByRole('tooltip').innerText(), 'Snapshot');
  assert.equal(await page.getByRole('button', { name: 'Take snapshot', exact: true }).getAttribute('title'), null);
  await page.evaluate(() => window.harness.open('next.txt'));
  await waitValue('root-a next');
  assert.equal(await page.getByRole('button', { name: 'Inspect notes', exact: true }).count(), 0);
  await page.evaluate(() => {
    window.harness.rendererCallbacks.get('root-a').onNavigationActionsChange([
      { id: 'next', label: 'Inspect next', icon: 'span', onInvoke() {} }
    ]);
    window.retiredNavbar([]);
  });
  await page.getByRole('button', { name: 'Inspect next', exact: true }).waitFor();
  await page.evaluate(() => window.retiredNavbar([{ id: 'stale', label: 'Stale action', icon: 'span', onInvoke() {} }]));
  assert.equal(await page.getByRole('button', { name: 'Stale action', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Inspect next', exact: true }).count(), 1);
});

test("a departing renderer flushes its own state on file changes and reloads, but never into another root", async () => {
  await reset();
  await page.evaluate(() => { window.harness.cleanupWrites.set('root-a:notes.txt', { selection: 'last frame' }); window.harness.open('next.txt'); });
  await waitValue('root-a next');
  assert.deepEqual(await page.evaluate(() => window.harness.state.renderers['["notes.txt","in-memory"]']), { selection: 'last frame' });
  const key = await page.getByTestId('document-key').textContent();
  await page.evaluate(() => { window.harness.cleanupWrites.set('root-a:next.txt', { drawing: 'pending stroke' }); window.harness.rendererCallbacks.get('root-a').reload(); });
  await page.waitForFunction(previous => document.querySelector('[data-testid="document-key"]')?.textContent !== previous, key);
  await waitValue('root-a next');
  assert.deepEqual(await page.evaluate(() => window.harness.state.renderers['["next.txt","in-memory"]']), { drawing: 'pending stroke' });
  await page.evaluate(() => { window.harness.cleanupWrites.set('root-a:next.txt', { drawing: 'wrong root' }); window.harness.setRoot('root-b'); });
  await waitValue('root-b next');
  assert.deepEqual(await page.evaluate(() => window.harness.state.renderers['["next.txt","in-memory"]']), { drawing: 'pending stroke' });
});

test("the navbar names the open file by its name, and nothing while the host has not named it", async () => {
  await reset();
  const name = () => page.locator('[data-file-name]');
  await page.evaluate(() => { window.harness.a.add('nested/deep/file.txt'); window.harness.open('nested/deep/file.txt'); });
  await waitValue('added');
  assert.equal(await name().textContent(), 'file.txt');
  // No crumbs: the folders are the explorer's to show.
  assert.equal(await page.locator('[data-crumb]').count(), 0);
  await page.evaluate(() => window.harness.open('next.txt'));
  await waitValue('root-a next');
  await page.evaluate(() => window.harness.navigationPath(null));
  await name().waitFor({ state: 'detached' });
  assert.equal(await page.getByTestId('file-actions').count(), 0);
  assert.equal(await document().inputValue(), 'root-a next');
  await page.evaluate(() => window.harness.navigationPath(undefined));
  await page.locator('[data-file-name]', { hasText: 'next.txt' }).waitFor();
});

test("late trash completion does not issue new requests into the previous root", async () => {
  await reset();
  await page.getByTestId('tree-toggle').click();
  await page.locator('[role="treeitem"][data-path="notes.txt"]').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Move to Trash' }).click();
  await page.evaluate(() => window.harness.setRoot('root-b'));
  await waitValue('root-b original');
  const requests = await page.evaluate(() => window.harness.events.filter(event => event === 'root-a:list').length);
  await page.evaluate(() => window.harness.a.releaseTrash());
  await page.waitForTimeout(20);
  assert.equal(await page.evaluate(() => window.harness.events.filter(event => event === 'root-a:list').length), requests);
});

test("catalog arrival restarts the initial pending directory listing", async () => {
  await page.goto(`http://127.0.0.1:${server.address().port}/?initialList=1`);
  await waitValue('root-a original');
  await page.getByTestId('tree-toggle').click();
  await page.getByText('Loading files…', { exact: true }).waitFor();
  await page.evaluate(() => window.harness.a.add('catalog-file.txt'));
  await page.locator('[role="treeitem"][data-path="catalog-file.txt"]').waitFor();
  await page.locator('[role="treeitem"][data-path="notes.txt"]').waitFor();
  assert.equal(await page.getByText('Loading files…', { exact: true }).count(), 0);
  assert.ok(await page.evaluate(() => window.harness.events.filter(event => event === 'root-a:list').length >= 2));
});

test("the explorer floats over the view's left, inset like its tool strip, and opening it resizes nothing", async () => {
  await reset();
  const pane = page.getByTestId("primary");
  const view = () => pane.getByRole("textbox", { name: "Document", exact: true }).evaluate(element => element.closest('.overflow-hidden')?.getBoundingClientRect().toJSON());
  const before = await view();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  assert.deepEqual(await view(), before, "the view keeps its box");
  const [explorer, body] = await Promise.all([
    pane.locator('[data-file-explorer]').evaluate(element => element.getBoundingClientRect().toJSON()),
    pane.locator('[data-file-explorer]').evaluate(element => element.parentElement.getBoundingClientRect().toJSON()),
  ]);
  // As tall as its rows: a short tree leaves the view below it...
  assert.deepEqual([explorer.left - body.left, explorer.top - body.top], [8, 8]);
  assert.ok(body.bottom - explorer.bottom > 8, `a short tree leaves room below it: ${body.bottom - explorer.bottom}px`);
  // ...and a long one stops 8px above the view's bottom, its list scrolling.
  await page.evaluate(() => { for (let index = 0; index < 80; index += 1) window.harness.a.add(`many-${String(index).padStart(2, "0")}.txt`); });
  await page.locator('[role="treeitem"][data-path="many-00.txt"]').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="primary"] [role="tree"]')?.scrollHeight > document.querySelector('[data-testid="primary"] [role="tree"]')?.clientHeight);
  const tall = await pane.locator('[data-file-explorer]').evaluate(element => element.getBoundingClientRect().toJSON());
  assert.equal(Math.round(body.bottom - tall.bottom), 8, "a long tree fills the view's height, less its inset");
  // A pick in it keeps it up on a wide view, beside the file it opened.
  await page.locator('[role="treeitem"][data-path="next.txt"]').click();
  await waitValue("root-a next");
  assert.equal(await page.getByRole("tree").count(), 1);
});

test("a narrow empty tab asks for a file too, and a file picked in its sheet opens with nothing over it", async () => {
  await reset();
  const pane = page.getByTestId('primary');
  await pane.evaluate(element => { element.parentElement.style.width = '560px'; });
  await page.waitForFunction(() => document.querySelector('[data-viewer-layout]')?.dataset.viewerLayout === 'mobile');
  // A file opens with no sheet over it on a narrow viewer...
  assert.equal(await page.getByRole("tree").count(), 0);
  // ...and with no file, the sheet is the person's to open, from the explorer's toggle.
  await page.evaluate(() => window.harness.open(null));
  await page.getByText("Select file", { exact: true }).waitFor();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  assert.equal(await page.getByTestId("tree-toggle").getAttribute("aria-pressed"), "true");
  // A host hands focus back to whatever opened the tab (a closing menu's trigger): that is not a
  // dismissal, and the tree stays.
  await page.evaluate(() => { const outside = document.createElement("button"); outside.textContent = "New tab"; document.body.append(outside); outside.focus(); });
  await page.waitForTimeout(100);
  assert.equal(await page.getByRole("tree").count(), 1, "focus elsewhere does not dismiss the sheet");
  await page.locator('[role="treeitem"][data-path="next.txt"]').click();
  await waitValue("root-a next");
  assert.equal(await page.getByRole("tree").count(), 0, "the sheet closes on the pick");
  await pane.evaluate(element => { element.parentElement.style.width = ''; });
});

test("the renderer is not re-rendered by the frame's own chrome: a panel drag or a resize within a layout", async () => {
  await reset();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  await page.waitForTimeout(100);
  const before = await page.evaluate(() => window.harness.renders["root-a"]);
  for (const width of [320, 340, 360, 400]) await page.evaluate(next => window.harness.width(next), width);
  await page.setViewportSize({ width: 1180, height: 800 });
  await page.setViewportSize({ width: 1240, height: 800 });
  await page.waitForTimeout(100);
  assert.equal(await page.getByRole("tree").count(), 1);
  assert.equal(await page.evaluate(() => window.harness.renders["root-a"]), before, "no renderer render for a width that does not cross the breakpoint");
});

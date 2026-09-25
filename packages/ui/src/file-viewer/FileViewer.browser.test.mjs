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
  temporary = await mkdtemp(join(tmpdir(), "hardcore-file-viewer-browser-"));
  await build({ entryPoints: [fileURLToPath(new URL("./harness/index.tsx", import.meta.url))], outfile: join(temporary, "harness.js"), bundle: true, format: "esm", platform: "browser", jsx: "automatic" });
  const bundle = await readFile(join(temporary, "harness.js"));
  server = createServer((request, response) => {
    if (request.url === "/harness.js") { response.setHeader("Content-Type", "text/javascript"); response.end(bundle); }
    else { response.setHeader("Content-Type", "text/html"); response.end('<!doctype html><html><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
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
  await page.getByTestId("crumb-actions").click();
  assert.equal(await page.getByRole("menuitem", { name: /Reveal|Open with|Move to trash/ }).count(), 0);
  await page.getByRole("menuitem", { name: /^Rename/ }).click();
  await page.getByRole("textbox", { name: "Rename file", exact: true }).fill("renamed.txt");
  await page.getByRole("textbox", { name: "Rename file", exact: true }).press("Enter");
  await page.getByRole("button", { name: "Browse renamed.txt", exact: true }).waitFor();
  // The tab follows the file to its new name through the host, and keeps the panel it had.
  assert.deepEqual(await page.evaluate(() => window.harness.opened.at(-1)), { path: "renamed.txt", options: { target: "current", panel: "tree" } });
  await page.getByRole("tree").dispatchEvent("contextmenu", { button: 2 });
  await page.getByRole("menuitem", { name: /New file/ }).click();
  await page.getByRole("textbox", { name: "New file name", exact: true }).fill("created.txt");
  await page.getByRole("textbox", { name: "New file name", exact: true }).press("Enter");
  await page.getByRole("button", { name: "Browse created.txt", exact: true }).waitFor();
  // Made in the tree, the file is opened the way a pick there opens one: with the tree.
  assert.deepEqual(await page.evaluate(() => window.harness.opened.at(-1)), { path: "created.txt", options: { target: "new", panel: "tree" } });
  assert.equal(await page.getByRole("tree").count(), 1);
});
test("an empty tab opens on the tree, a pick in the tree opens the file with the tree, and a crumb opens it on its own default", async () => {
  // With no file to show, the tree is the one thing to reach for: it is what an empty tab opens on.
  await reset();
  await page.evaluate(() => window.harness.open(null));
  await page.getByRole("tree").waitFor();
  assert.equal(await page.getByTestId("tree-toggle").getAttribute("aria-pressed"), "true");

  // A pick in the tree asks the host for the file WITH the tree, so a person walks it file by
  // file — the empty tab's tree too, which nobody opened by hand.
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

  // A crumb is not the tree: it opens the file on its own default — for a document, no panel —
  // and not on whatever the last file had open (here, its renderer's Details).
  await page.evaluate(() => window.harness.open("notes.txt"));
  await waitValue("root-a original");
  await page.getByRole("button", { name: "Details", exact: true }).click();
  await page.getByText("Injected panel").waitFor();
  await page.getByRole("button", { name: "Browse notes.txt", exact: true }).click();
  await page.getByRole("menu", { name: "Browse notes.txt" }).getByRole("menuitem", { name: "next.txt", exact: true }).click();
  await waitValue("root-a next");
  assert.deepEqual(await page.evaluate(() => window.harness.opened.at(-1)), { path: "next.txt", options: { target: "current" } });
  assert.equal(await page.getByText("Injected panel").count(), 0, "the last file's panel is not the next one's");
  assert.equal(await page.getByRole("tree").count(), 0);
  assert.equal(await page.evaluate(() => window.harness.state.panel), null, "the field is back to the file's own default");
});
test("preview hides shared chrome, another document restores it, and widths stay bounded", async () => {
  await reset();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  await page.evaluate(() => window.harness.width(99999));
  // The width is bounded at the column's maximum. (The store write renders on React's
  // schedule, so the handle is read once it has.)
  const handle = page.getByRole("separator", { name: "Resize Hide files panel" });
  await page.waitForFunction(() => document.querySelector('[role="separator"][aria-label="Resize Hide files panel"]')?.getAttribute("aria-valuenow") !== "300");
  assert.equal(await handle.getAttribute("aria-valuenow"), await handle.getAttribute("aria-valuemax"));
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  assert.equal(await page.getByTestId("tree-toggle").count(), 0);
  assert.equal(await page.getByRole("tree").count(), 0);
  await page.evaluate(() => window.harness.open("next.txt"));
  await waitValue("root-a next");
  await page.getByTestId("tree-toggle").waitFor();
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
test("a former renderer cannot change the new root's panels, state or preview", async () => {
  await reset();
  await page.getByTestId("tree-toggle").click();
  await page.getByRole("tree").waitFor();
  await page.evaluate(() => window.harness.setRoot("root-b"));
  await waitValue("root-b original");
  await page.evaluate(() => {
    const stale = window.harness.rendererCallbacks.get("root-a");
    stale.onPanelOpen("details"); stale.onStateChange({ from: "old root" }); stale.onChromeVisibilityChange(false);
  });
  await page.getByTestId("tree-toggle").waitFor();
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

test("host breadcrumb policy stays scoped to the active document", async () => {
  await reset();
  await page.evaluate(() => { window.harness.a.add('nested/deep/file.txt'); window.harness.narrowCrumbs(true); window.harness.open('nested/deep/file.txt'); });
  await waitValue('added');
  await page.getByRole('button', { name: 'Browse nested/deep', exact: true }).waitFor();
  await page.evaluate(() => window.harness.narrowCrumbs(false));
  await page.getByRole('button', { name: 'Browse nested', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Browse deep', exact: true }).waitFor();
  await page.evaluate(() => window.harness.open('next.txt'));
  await waitValue('root-a next');
  await page.evaluate(() => window.harness.navigationPath(null));
  assert.equal(await page.getByRole('navigation', { name: 'Breadcrumb' }).getByRole('button').count(), 0);
  assert.equal(await document().inputValue(), 'root-a next');
  await page.evaluate(() => window.harness.navigationPath(undefined));
  await page.getByRole('button', { name: 'Browse next.txt', exact: true }).waitFor();
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
  await page.getByText('Reading…', { exact: true }).waitFor();
  await page.evaluate(() => window.harness.a.add('catalog-file.txt'));
  await page.locator('[role="treeitem"][data-path="catalog-file.txt"]').waitFor();
  await page.locator('[role="treeitem"][data-path="notes.txt"]').waitFor();
  assert.equal(await page.getByText('Reading…', { exact: true }).count(), 0);
  assert.ok(await page.evaluate(() => window.harness.events.filter(event => event === 'root-a:list').length >= 2));
});

test("mobile breadcrumbs show only the file and its actions across a single breakpoint", async () => {
  await reset();
  await page.evaluate(() => { window.harness.a.add('nested/deep/file.txt'); window.harness.open('nested/deep/file.txt'); });
  await page.getByRole('button', { name: 'Browse file.txt', exact: true }).waitFor();
  const pane = page.getByTestId('primary');
  await pane.evaluate(element => { element.parentElement.style.width = '390px'; });
  await page.waitForFunction(() => document.querySelector('[data-viewer-layout]')?.dataset.viewerLayout === 'mobile');
  assert.equal(await pane.locator('[data-crumb="directory"], [data-crumb="ellipsis"]').count(), 0);
  assert.equal(await pane.getByTestId('crumb-actions').count(), 1);
  await pane.evaluate(element => { element.parentElement.style.width = '720px'; });
  await page.waitForFunction(() => document.querySelector('[data-viewer-layout]')?.dataset.viewerLayout === 'desktop');
  assert.equal(await pane.locator('[data-crumb="directory"]').count(), 2);
});

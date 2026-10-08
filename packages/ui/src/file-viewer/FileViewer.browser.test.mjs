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
  await payload().waitFor();
}
const pane = () => page.getByTestId("primary");
const payload = () => pane().getByTestId("payload");
async function waitPayload(value) { await page.waitForFunction((expected) => document.querySelector('[data-testid="primary"] [data-testid="payload"]')?.textContent === expected, value); }
// Two frames on: what a change asked for has been drawn.
const settle = () => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

test("the file's name opens the explorer under it, over the view, its long folder scrolling inside it; a pick is shown through the host and puts it away", async () => {
  await reset();
  await waitPayload("root-a notes");
  await page.evaluate(() => { for (let index = 0; index < 80; index += 1) window.harness.a.files.set(`/work/many-${String(index).padStart(2, "0")}.txt`, "many"); });
  const view = () => payload().evaluate((element) => element.closest(".overflow-hidden")?.getBoundingClientRect().toJSON());
  const before = await view();
  await pane().locator("[data-file-name]").click();
  const explorer = page.locator("[data-file-explorer]");
  await explorer.locator('[data-path="/work/many-00.txt"]').waitFor();
  // Measured where it comes to rest, once its opening animation has run.
  await explorer.evaluate((node) => Promise.all(node.getAnimations({ subtree: true }).map((animation) => animation.finished)));
  assert.deepEqual(await view(), before, "the view keeps its box");
  const [name, box] = await Promise.all([pane().locator("[data-file-name]").boundingBox(), explorer.boundingBox()]);
  assert.ok(box.y >= name.y + name.height && box.y + box.height <= page.viewportSize().height, `under the name, inside the page: ${JSON.stringify([name, box])}`);
  assert.ok(await explorer.locator('[data-slot="scroll-area-viewport"]').evaluate((element) => element.scrollHeight > element.clientHeight), "its rows scroll inside it");
  await explorer.locator('[data-path="/work/next.txt"]').click();
  await waitPayload("root-a next");
  assert.deepEqual(await page.evaluate(() => window.harness.opened), ["/work/next.txt"]);
  // The pick puts the explorer away (once its closing animation has run).
  await explorer.waitFor({ state: "detached" });
});

test("the explorer opens with its filter taking the keyboard, under a breadcrumb of whole folder names: those that do not fit beside the folder it is in are the ellipsis's", async () => {
  await reset();
  const deep = "/work/assemblies/STEP/planetary_gear_assembly/planetary_gear_assembly.txt";
  await page.evaluate((path) => { window.harness.a.files.set(path, "root-a planetary"); window.harness.open(path); }, deep);
  await waitPayload("root-a planetary");
  await pane().locator("[data-file-name]").click();
  const crumbs = page.locator('[data-file-explorer] nav[aria-label="Folders"] button');
  await page.locator('[data-file-explorer] [data-path$="planetary_gear_assembly.txt"]').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Filter files");
  // Every crumb is its folder's whole name; "assemblies" did not fit beside the rest, so it went into the ellipsis.
  assert.deepEqual(await crumbs.evaluateAll((buttons) => buttons.map((button) => [button.getAttribute("aria-label") || button.textContent, button.scrollWidth <= button.clientWidth])),
    [["Folders above", true], ["STEP", true], ["planetary_gear_assembly", true]]);
  await crumbs.first().click();
  assert.deepEqual(await page.getByRole("menuitem").allTextContents(), ["/", "work", "assemblies"]);
  await page.keyboard.press("Escape");
});

test("sources, instances and cancelled opens stay isolated", async () => {
  await reset();
  await page.evaluate(() => window.harness.setRoot("root-b"));
  await waitPayload("root-b notes");
  await page.evaluate(() => { window.harness.setRoot("root-a"); window.harness.second(true); });
  await waitPayload("root-a notes");
  assert.equal(await page.getByTestId("secondary").getByTestId("payload").textContent(), "root-b notes");
  await page.evaluate(() => window.harness.second(false));
  await page.evaluate(() => window.harness.open("/work/slow.txt"));
  await pane().getByRole("status").filter({ hasText: "Opening" }).waitFor();
  await page.evaluate(() => window.harness.open("/work/next.txt"));
  await waitPayload("root-a next");
  assert.ok(await page.evaluate(() => window.harness.events.includes("root-a:aborted")));
  assert.ok(await page.evaluate(() => window.harness.events.includes("root-b:/work/notes.txt:disposed")));
});

test("a former renderer cannot change the new source's state", async () => {
  await reset();
  await page.evaluate(() => window.harness.setRoot("root-b"));
  await waitPayload("root-b notes");
  await page.evaluate(() => window.harness.rendererCallbacks.get("root-a").onStateChange({ from: "old root" }));
  await settle();
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
  await page.evaluate(() => window.harness.open('/work/next.txt'));
  await waitPayload('root-a next');
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

test("a departing renderer flushes its own state on file changes and reloads, but never into another source", async () => {
  await reset();
  await page.evaluate(() => { window.harness.cleanupWrites.set('root-a:/work/notes.txt', { selection: 'last frame' }); window.harness.open('/work/next.txt'); });
  await waitPayload('root-a next');
  assert.deepEqual(await page.evaluate(() => window.harness.state.renderers['["/work/notes.txt","in-memory"]']), { selection: 'last frame' });
  const mount = await pane().getByTestId('mount').textContent();
  await page.evaluate(() => { window.harness.cleanupWrites.set('root-a:/work/next.txt', { drawing: 'pending stroke' }); window.harness.rendererCallbacks.get('root-a').reload(); });
  await page.waitForFunction(previous => document.querySelector('[data-testid="primary"] [data-testid="mount"]')?.textContent !== previous, mount);
  await waitPayload('root-a next');
  assert.deepEqual(await page.evaluate(() => window.harness.state.renderers['["/work/next.txt","in-memory"]']), { drawing: 'pending stroke' });
  await page.evaluate(() => { window.harness.cleanupWrites.set('root-a:/work/next.txt', { drawing: 'wrong source' }); window.harness.setRoot('root-b'); });
  await waitPayload('root-b next');
  assert.deepEqual(await page.evaluate(() => window.harness.state.renderers['["/work/next.txt","in-memory"]']), { drawing: 'pending stroke' });
});

test("the renderer is not re-rendered by the frame's own chrome: a navbar action it published or a resize within a layout", async () => {
  await reset();
  await settle();
  const before = await page.evaluate(() => window.harness.renders["root-a"]);
  await page.evaluate(() => window.harness.rendererCallbacks.get("root-a").onNavigationActionsChange([{ id: "fixture", label: "Inspect notes", icon: "span", onInvoke() {} }]));
  await pane().getByRole("button", { name: "Inspect notes", exact: true }).waitFor();
  await page.setViewportSize({ width: 1180, height: 800 });
  await page.setViewportSize({ width: 1240, height: 800 });
  await settle();
  assert.equal(await page.evaluate(() => window.harness.renders["root-a"]), before, "no renderer render for its own navbar action, or a width that does not cross the breakpoint");
});

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
// Which file generation owns a write or an action is `FileViewerGenerations.test.tsx`'s (jsdom, over
// this harness's App); here, what needs a layout. Two frames on: what a change asked for has been drawn.
const settle = () => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

test("a document in a project has the project's name before its own: in a narrow row and on a phone a folder tile named by it, the document's name whole; a press goes to the home at it", async () => {
  await reset();
  await waitPayload("root-a notes");
  assert.equal(await pane().locator("[data-navbar-project]").count(), 0, "a document in no project has none");
  const name = "a-project-with-a-rather-long-name-indeed";
  await page.evaluate((name) => window.harness.project({ id: "p1", name, root: "/work", documents: [] }), name);
  const crumb = pane().locator("[data-navbar-project]");
  const text = crumb.getByRole("button", { name, exact: true });
  await text.waitFor();
  const whole = (locator) => locator.evaluate((element) => element.scrollWidth <= element.clientWidth);
  assert.ok(await whole(text.locator("span")), "a wide row has it whole");
  // A narrow row (a desktop's, its controls left little room): the folder tile, the control's size, and the document's name whole.
  const nav = '[data-testid="primary"] [data-viewer-navbar] nav';
  await page.evaluate((nav) => { document.querySelector(nav).style.maxWidth = "140px"; }, nav);
  const tile = crumb.locator("[data-project-tile]");
  await tile.waitFor();
  assert.deepEqual(await tile.evaluate((element) => { const box = element.getBoundingClientRect(); return [element.getAttribute("aria-label"), box.width, box.height]; }), [name, 28, 28]);
  assert.ok(await whole(pane().locator("[data-file-name] span")), "the document's name whole beside the tile");
  await tile.click();
  assert.deepEqual(await page.evaluate(() => window.harness.events.filter((event) => event.startsWith("project:"))), ["project:p1"]);
  // Room again: the name again.
  await page.evaluate((nav) => { document.querySelector(nav).style.maxWidth = ""; }, nav);
  await text.waitFor();
  // A phone (the viewer under 600px): the tile at the phone's control, 36px.
  await page.evaluate(() => { document.querySelector('[data-testid="primary"]').parentElement.style.width = "420px"; });
  await page.waitForFunction(() => document.querySelector('[data-testid="primary"] [data-project-tile]')?.getBoundingClientRect().width === 36);
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

// A library card's picture is drawn by a viewer of its own, out of sight at 480 × 360 (`OffscreenPicture.tsx`). That viewer
// is under the phone breakpoint, and the page's type once followed it: Home's text grew a step while its cards got pictures.
test("a viewer drawn out of sight for a picture never changes the page: its layout pinned, no data-viewer-layout, the page's type its own", async () => {
  await reset();
  await page.setViewportSize({ width: 1280, height: 800 });
  await settle();
  const type = () => page.evaluate(() => ({ xs: getComputedStyle(document.documentElement).getPropertyValue("--cad-text-xs").trim(),
    name: getComputedStyle(document.querySelector('[data-testid="primary"] [data-file-name]')).fontSize,
    layouts: [...document.querySelectorAll("[data-viewer-layout]")].map((node) => node.getAttribute("data-viewer-layout")) }));
  const desktop = await type();
  assert.deepEqual(desktop.layouts, ["desktop"]);
  // As OffscreenPicture draws it: pinned, it neither measures nor carries the attribute the page's stylesheet reads.
  await page.evaluate(() => window.harness.picture("pinned"));
  await page.getByTestId("picture").locator("[data-viewer-pinned-layout]").waitFor({ state: "attached" });
  await settle();
  assert.deepEqual(await type(), desktop, "a pinned picture viewer leaves the page as it was");
  assert.equal(await page.getByTestId("picture").locator("[data-viewer-pinned-layout]").getAttribute("data-viewer-pinned-layout"), "mobile");
  // And a viewer in the picture's box that measured itself a phone's is still not the page's.
  await page.evaluate(() => window.harness.picture("measured"));
  await page.getByTestId("picture").locator('[data-viewer-layout="mobile"]').waitFor({ state: "attached" });
  await settle();
  const measured = await type();
  assert.deepEqual([measured.xs, measured.name], [desktop.xs, desktop.name], "a phone-sized viewer out of sight never sets the page's type");
  await page.evaluate(() => window.harness.picture("none"));
});

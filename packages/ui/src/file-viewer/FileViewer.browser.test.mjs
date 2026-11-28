import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import { build } from "esbuild";
import { chromium } from "playwright";
import en from "../i18n/locales/en.js";

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

test("the update button is the navbar's outermost control, and a failed update is the viewer's alert card, centred over the view, until its X or Escape", async () => {
  await reset();
  await waitPayload("root-a notes");
  await page.evaluate(() => window.harness.update("failed"));
  const navbar = pane().locator("[data-viewer-navbar]");
  const button = navbar.locator("[data-update]");
  await button.waitFor();
  const controls = await navbar.evaluate((row) => [...row.querySelectorAll("button")].map((node) => node.getBoundingClientRect().right));
  const [row, box] = await Promise.all([navbar.boundingBox(), button.boundingBox()]);
  assert.equal(Math.max(...controls), box.x + box.width, "the last of the row's controls, outermost");
  assert.ok(row.x + row.width - (box.x + box.width) <= 16, `at the row's right end: ${JSON.stringify([row, box])}`);
  // The one alert card, centred over what is under the navbar, as a view's card is over the view.
  const card = pane().locator("[data-host-alert] [role=alert]");
  await card.waitFor();
  const [at, body] = await Promise.all([card.boundingBox(), payload().evaluate((element) => element.closest(".overflow-hidden").parentElement.getBoundingClientRect().toJSON())]);
  assert.ok(Math.abs(at.x + at.width / 2 - (body.x + body.width / 2)) <= 1 && Math.abs(at.y + at.height / 2 - (body.y + body.height / 2)) <= 1,
    `centred over the view: ${JSON.stringify([body, at])}`);
  assert.ok(at.y >= row.y + row.height, "under the navbar");
  assert.equal(await card.getByRole("heading").textContent(), "Couldn’t update to 0.9.1");
  assert.deepEqual((await card.innerText()).split("\n").filter(Boolean), ["Couldn’t update to 0.9.1",
    en["update.cause.in_use"], "Details", en["update.retry"]]);
  await payload().click();
  await settle();
  assert.ok(await card.isVisible(), "a press elsewhere leaves it");
  await page.keyboard.press("Escape");
  await card.waitFor({ state: "detached" });
  // Put away: its icon, first of the right-hand controls, brings it back; its X puts it away again.
  const icon = navbar.getByRole("button", { name: "Couldn’t update to 0.9.1" });
  const right = await navbar.evaluate((row) => [...row.lastElementChild.querySelectorAll("button")].map((node) => node.getAttribute("aria-label")));
  assert.equal(right[0], "Couldn’t update to 0.9.1", `the first of them: ${right}`);
  await icon.click();
  await card.waitFor();
  await card.getByRole("button", { name: "Dismiss" }).click();
  await card.waitFor({ state: "detached" });
  assert.deepEqual(await page.evaluate(() => window.harness.events.filter((event) => ["dismiss", "reopen", "update"].includes(event))), ["dismiss", "reopen", "dismiss"]);
  await page.evaluate(() => window.harness.update("none"));
});

test("the update button is the navbar's top-right corner, over a file and over the home, at every width: its two looks, their hints, and a click that acts at once", async () => {
  await reset();
  await waitPayload("root-a notes");
  const navbar = pane().locator("[data-viewer-navbar]");
  const button = navbar.locator("[data-update]");
  const box = (locator) => locator.evaluate((node) => node.getBoundingClientRect().toJSON());
  for (const width of [1600, 1280, 390]) {
    await page.setViewportSize({ width, height: 800 });
    await page.evaluate((next) => { document.querySelector("#root > div").style.width = `${next}px`; }, width);
    for (const where of ["home", "file"]) {
      await page.evaluate((path) => window.harness.open(path), where === "home" ? null : "/work/notes.txt");
      if (where === "home") await navbar.locator("[data-navbar-home-right]").getByRole("button", { name: "Import", exact: true }).waitFor();
      else await waitPayload("root-a notes");
      for (const [state, tip] of [["behind", "Update"]]) {
        await page.evaluate((next) => window.harness.update(next), state);
        await navbar.locator('[data-update=""]').waitFor();
        await settle();
        const [row, at, pad, rights] = [await box(navbar), await box(button), await navbar.evaluate((node) => parseFloat(getComputedStyle(node).paddingRight)),
          await navbar.evaluate((node) => [...node.querySelectorAll("button")].map((control) => control.getBoundingClientRect().right))];
        const where_ = `${where} at ${width}, ${state}`;
        assert.equal(Math.max(...rights), at.right, `the navbar's last control: ${where_}`);
        assert.ok(Math.abs(row.right - pad - at.right) <= 0.5, `on the row's right end, less its padding: ${where_} ${JSON.stringify([row, pad, at])}`);
        if (where === "home") {
          // The home's own controls (the search and Import) end short of the button, which keeps the row's end.
          const end = (await box(navbar.locator("[data-navbar-home-right]"))).right;
          assert.ok(end <= at.left - 8, `short of the button: ${where_} ${end} ${at.left}`);
        }
        // Its hint under a resting pointer. A hover the hint did not take is tried again, as a person moves the pointer
        // again: three hovers, each awaited, and the place and state said where none was taken.
        const hint = page.locator('[data-slot="tooltip-content"]');
        for (let tries = 1; ; tries += 1) {
          await page.mouse.move(1, 790);
          await button.hover();
          try {
            await hint.waitFor({ timeout: 3000 });
            break;
          } catch (error) {
            if (tries === 3) throw new Error(`no hint after three hovers: ${where_}`, { cause: error });
          }
        }
        assert.equal(await page.getByRole("tooltip").textContent(), tip, `its hint: ${where_}`);
        await page.mouse.move(1, 790);
        await hint.waitFor({ state: "detached" });
      }
      // A click acts at once: the ring.
      for (const [state, after] of [["behind", "working"]]) {
        await page.evaluate((next) => window.harness.update(next), state);
        await button.click();
        await navbar.locator(`[data-update="${after}"]`).waitFor();
        assert.equal(await page.locator('[role="dialog"]').count(), 0, "nothing opens");
      }
    }
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.evaluate(() => { document.querySelector("#root > div").style.width = "1000px"; window.harness.update("none"); window.harness.open("/work/notes.txt"); });
});

// A viewer that is not the page's own (`FileViewerProps.layout`), here out of sight at 480 × 360, is under the phone
// breakpoint: the page's type must not follow it.
test("a viewer that is not the page's own never changes the page: its layout pinned, no data-viewer-layout, the page's type its own", async () => {
  await reset();
  await page.setViewportSize({ width: 1280, height: 800 });
  await settle();
  const type = () => page.evaluate(() => ({ xs: getComputedStyle(document.documentElement).getPropertyValue("--cad-text-xs").trim(),
    name: getComputedStyle(document.querySelector('[data-testid="primary"] [data-file-name]')).fontSize,
    layouts: [...document.querySelectorAll("[data-viewer-layout]")].map((node) => node.getAttribute("data-viewer-layout")) }));
  const desktop = await type();
  assert.deepEqual(desktop.layouts, ["desktop"]);
  // Pinned, it neither measures nor carries the attribute the page's stylesheet reads.
  await page.evaluate(() => window.harness.picture("pinned"));
  await page.getByTestId("picture").locator("[data-viewer-pinned-layout]").waitFor({ state: "attached" });
  await settle();
  assert.deepEqual(await type(), desktop, "a pinned viewer leaves the page as it was");
  assert.equal(await page.getByTestId("picture").locator("[data-viewer-pinned-layout]").getAttribute("data-viewer-pinned-layout"), "mobile");
  await page.evaluate(() => window.harness.picture("none"));
});

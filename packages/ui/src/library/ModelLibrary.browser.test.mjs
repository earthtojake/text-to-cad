import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import { build } from "esbuild";
import { chromium } from "playwright";

// The home as it is drawn (`docs/viewer-ux.md`, "The home"): what needs a layout, a real link or a real key. What it
// lists, counts and asks of its host is `ModelLibrary.test.tsx`'s.
let server, browser, temporary, origin;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), "text-to-cad-home-browser-"));
  await build({ entryPoints: [fileURLToPath(new URL("./harness/index.tsx", import.meta.url))], outfile: join(temporary, "harness.js"), bundle: true, format: "esm", platform: "browser", jsx: "automatic", loader: { ".svg": "dataurl" } });
  const bundle = await readFile(join(temporary, "harness.js"));
  // The package's own stylesheet, so the page is laid out as a host lays it out.
  const styles = await readFile(fileURLToPath(new URL("../../dist/styles.css", import.meta.url)));
  server = createServer((request, response) => {
    if (request.url === "/harness.js") { response.setHeader("Content-Type", "text/javascript"); response.end(bundle); }
    else if (request.url === "/styles.css") { response.setHeader("Content-Type", "text/css"); response.end(styles); }
    else { response.setHeader("Content-Type", "text/html"); response.end('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><style>html,body{height:100%;margin:0}</style></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true });
});
after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); if (temporary) await rm(temporary, { recursive: true, force: true }); });

/** The home in a window of its own, at `query`: closed by the test that opened it. */
async function home(query = "", viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.setDefaultTimeout(10_000);
  page.on("pageerror", (error) => console.error("Browser harness error:", error.message));
  await page.goto(`${origin}/?${query}`);
  await page.locator(".cad-library-card, .cad-library-row").first().waitFor();
  return { context, page };
}
const box = (locator) => locator.evaluate((node) => { const { x, y, width, height, right, bottom } = node.getBoundingClientRect(); return { x, y, width, height, right, bottom }; });
const style = (locator, ...names) => locator.evaluate((node, wanted) => { const computed = getComputedStyle(node); return wanted.map((name) => computed[name]); }, names);
// A colour as the browser computes it, from a token: what the stylesheet says a surface is.
const token = (page, name) => page.evaluate((variable) => { const probe = document.createElement("i"); probe.style.color = `var(${variable})`; document.body.append(probe); const colour = getComputedStyle(probe).color; probe.remove(); return colour; }, name);

test("a wide home has its places in a 232px sidebar on the panel's surface, full height under the navbar, and the place on screen beside it", async () => {
  const { context, page } = await home();
  try {
    const navbar = await box(page.locator("[data-viewer-navbar]"));
    const sidebar = page.getByRole("navigation", { name: "Places" });
    const side = await box(sidebar);
    assert.deepEqual([side.x, side.width, side.y, side.bottom], [0, 232, navbar.bottom, 900], "232px at the window's edge, from the navbar to the bottom");
    assert.deepEqual(await style(sidebar, "backgroundColor", "borderRightWidth"), [await token(page, "--sidebar"), "1px"]);
    // The navbar's row over it is the row over a file: its own 8px a side, on no centred column.
    assert.deepEqual(await style(page.locator("[data-viewer-navbar]"), "paddingLeft", "paddingRight"), ["8px", "8px"]);
    // Its rows are the panel's: 28px, the panel's one type size, their glyph on the 16px inset and their count ending on it.
    const pinned = sidebar.locator('[data-place="pinned"]');
    assert.deepEqual([(await box(pinned)).height, ...(await style(pinned, "fontSize", "lineHeight"))], [28, "12px", "16px"]);
    assert.equal((await box(pinned.locator("svg"))).x, 16);
    assert.equal(Math.round((await box(pinned.locator("span >> text=2"))).right), 232 - 1 - 16);
    // The place on screen is marked as an open tab is: the accent fill at medium weight.
    const recents = sidebar.locator('[data-place="recents"]');
    assert.deepEqual([await recents.getAttribute("aria-current"), ...(await style(recents, "backgroundColor", "fontWeight"))], ["page", await token(page, "--accent"), "500"]);
    assert.deepEqual(await style(pinned, "backgroundColor", "fontWeight"), ["rgba(0, 0, 0, 0)", "400"]);
    // A project whose folder is gone is muted.
    assert.equal((await style(sidebar.locator('[data-place="project:lamp"]'), "color"))[0], await token(page, "--muted-foreground"));
    // The place: its name the page's one larger text, 24px in from the sidebar and 20px under the navbar; Show, Sort and
    // the layout at the row's right end, every control the scale's 28px.
    const title = page.locator(".cad-library-title");
    assert.deepEqual([await title.textContent(), ...(await style(title, "fontSize", "lineHeight", "fontWeight"))], ["Recents", "15px", "20px", "600"]);
    const toolbar = await box(page.locator(".cad-library-toolbar"));
    assert.deepEqual([toolbar.x, toolbar.y, toolbar.right], [232 + 24, navbar.bottom + 20, 1440 - 24]);
    for (const name of ["Show All", "Sort by Last activity", "Grid", "List"]) assert.equal((await box(page.getByRole("button", { name }))).height, 28, name);
    assert.equal(Math.round((await box(page.getByRole("button", { name: "List" }))).right), 1440 - 24);
    // Cards at least 232px a column, filling the place's width.
    const cards = await page.locator(".cad-library-card").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect()).map(({ x, width }) => [x, width]));
    assert.ok(cards.every(([, width]) => width >= 232), "every card at least 232px");
    assert.equal(cards[0][0], 232 + 24);
    // Recents says each card's project before its facts.
    assert.match(await page.getByRole("link", { name: "Open housing", exact: true }).locator(".cad-library-status").textContent(), /^gearbox · /);
  } finally { await context.close(); }
});

test("a card and a place are real links: a plain click stays in this view, and ⌘ or Ctrl and a click opens a new tab at the address", async () => {
  const { context, page } = await home();
  try {
    const card = page.getByRole("link", { name: "Open housing", exact: true });
    assert.equal(await card.getAttribute("href"), "/id-housing");
    const [tab] = await Promise.all([context.waitForEvent("page"), card.click({ modifiers: ["ControlOrMeta"] })]);
    assert.equal(tab.url(), `${origin}/id-housing`);
    await tab.close();
    // A place too; and this view has not moved.
    const project = page.locator('[data-place="project:gearbox"]');
    const [other] = await Promise.all([context.waitForEvent("page"), project.click({ modifiers: ["ControlOrMeta"] })]);
    assert.equal(other.url(), `${origin}/?place=gearbox`);
    await other.close();
    assert.deepEqual([page.url(), await page.locator(".cad-library-title").textContent()], [`${origin}/?`, "Recents"]);
    // A plain click shows the place here: no navigation of the page, its row the marked one.
    await project.click();
    await page.locator('.cad-library-title:text-is("gearbox")').waitFor();
    assert.deepEqual([page.url(), await project.getAttribute("aria-current"), context.pages().length], [`${origin}/?`, "page", 1]);
    // Its page: its folder from the home folder beside its name; a file of it no page has opened is a link as the rest are.
    assert.equal(await page.locator(".cad-library-path").textContent(), "~/work/gearbox");
    assert.equal(await page.getByRole("link", { name: "Open plate_0.dxf" }).getAttribute("href"), "/id-plate_0.dxf");
    // The keyboard: Up and Down walk the places, and Enter on one goes there.
    await project.focus();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-place")), "recents");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await page.locator('.cad-library-title:text-is("Pinned")').waitFor();
    assert.equal(page.url(), `${origin}/?`);
  } finally { await context.close(); }
});

test("the document just left is ringed in the brand's colour and in view, with the way back in the heading row, as a card and as a row", async () => {
  for (const layout of ["grid", "list"]) {
    // A window too short for the whole place: the one just left is scrolled to.
    const { context, page } = await home(`place=gearbox&from=plate_8.dxf&layout=${layout}`, { width: 1100, height: 420 });
    try {
      const ringed = page.locator("[data-from]");
      await ringed.waitFor();
      assert.equal(await ringed.count(), 1);
      assert.equal(await ringed.locator(".cad-library-open").getAttribute("aria-label"), "Open plate_8.dxf");
      const brand = await token(page, "--brand");
      const shadow = (await style(layout === "grid" ? ringed : ringed.locator(".cad-library-main"), "boxShadow"))[0];
      assert.ok(shadow.startsWith(brand) && /0px 0px 0px 2px/.test(shadow), `a 2px ring in the brand's colour: ${shadow}`);
      const place = await box(page.locator(".cad-library-content"));
      await page.waitForFunction(() => { const { top, bottom } = document.querySelector("[data-from]").getBoundingClientRect(); return top >= 40 && bottom <= innerHeight; });
      const at = await box(ringed);
      assert.ok(at.y >= place.y && at.bottom <= place.bottom, "the ringed document is in view");
      const back = page.getByRole("button", { name: "Back to plate_8.dxf" });
      assert.deepEqual([await back.locator("kbd").textContent(), await back.evaluate((node) => Boolean(node.closest(".cad-library-toolbar")))], ["Esc", true]);
    } finally { await context.close(); }
  }
});

test("a home narrower than 720px has no sidebar: its heading is the places' menu, and at a phone's width every control is a finger's", async () => {
  // A pane 700px wide in a wider window: the home measures itself, never the window.
  const pane = await home("width=700", { width: 1300, height: 800 });
  try {
    const { page } = pane;
    assert.equal(await page.getByRole("navigation", { name: "Places" }).count(), 0);
    const trigger = page.getByRole("button", { name: "Places: Recents" });
    assert.equal(await trigger.evaluate((node) => Boolean(node.closest("[data-navbar-home-left] h1"))), true, "the navbar's heading");
    assert.equal((await box(page.locator(".cad-library-content"))).x, 0);
    await trigger.click();
    const menu = page.getByRole("menu");
    assert.deepEqual(await menu.getByRole("menuitemradio").evaluateAll((items) => items.map((item) => [item.textContent, item.getAttribute("aria-checked")])),
      [["Recents", "true"], ["Pinned2", "false"], ["gearbox12", "false"], ["lamp", "false"], ["Standalone5", "false"]]);
    await menu.getByRole("menuitemradio", { name: /gearbox/ }).click();
    await page.getByRole("button", { name: "Places: gearbox" }).waitFor();
    assert.equal(await page.locator(".cad-library-card").count(), 12);
  } finally { await pane.context.close(); }
  const phone = await home("place=gearbox&from=housing", { width: 390, height: 844 });
  try {
    const { page } = phone;
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    // The scale's switch eases a button's size: measured once nothing is moving.
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    assert.equal(await page.getByRole("navigation", { name: "Places" }).count(), 0);
    // The phone's scale: 36px controls, each text 2px up; the place on 16px gutters, one card across.
    for (const name of ["Places: gearbox", "Grid", "List", "Sort by Last activity", "Back to housing", "Import", "Search models"]) {
      assert.equal((await box(page.getByRole("button", { name }).first())).height, 36, name);
    }
    assert.deepEqual(await style(page.getByRole("button", { name: "Places: gearbox" }), "fontSize"), ["15px"]);
    const cards = await page.locator(".cad-library-card").evaluateAll((nodes) => nodes.slice(0, 2).map((node) => { const { x, width } = node.getBoundingClientRect(); return [x, width]; }));
    assert.deepEqual(cards, [[16, 358], [16, 358]]);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "nothing wider than the phone");
    // Import is its icon alone there, still named.
    assert.equal((await box(page.getByRole("button", { name: "Import" }))).width, 36);
  } finally { await phone.context.close(); }
});

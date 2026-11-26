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
async function home(query = "", viewport = { width: 1440, height: 900 }, options = {}) {
  const context = await browser.newContext({ viewport, ...Object.fromEntries(Object.entries(options).filter(([name]) => name !== "waitFor")) });
  const page = await context.newPage();
  page.setDefaultTimeout(10_000);
  page.on("pageerror", (error) => console.error("Browser harness error:", error.message));
  const { waitFor = ".cad-library-card, .cad-library-row" } = options;
  await page.goto(`${origin}/?${query}`);
  await page.locator(waitFor).first().waitFor();
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
    // The sidebar is the viewer's panel (its surface), its places a navigation in it.
    const surface = page.locator("aside[data-library-sidebar]");
    const sidebar = page.getByRole("navigation", { name: "Places" });
    const side = await box(surface);
    assert.deepEqual([side.x, side.width, side.y, side.bottom], [0, 232, navbar.bottom, 900], "232px at the window's edge, from the navbar to the bottom");
    assert.deepEqual(await style(surface, "backgroundColor", "borderRightWidth"), [await token(page, "--sidebar"), "1px"]);
    assert.equal(await sidebar.evaluate((node) => Boolean(node.closest("aside[data-library-sidebar]"))), true);
    // The logo first, its drawn mark on the panel's 16px inset (its 16px image 14px in, the artwork 2px inside it); then
    // its toggle, the next 28px tile edge to edge with it; and no "Home": the place's title says where the person is.
    const toggle = page.locator('[data-viewer-navbar] [data-navbar-panel="left"]');
    assert.equal((await box(page.locator("[data-viewer-navbar] [data-navbar-logo] img"))).x + 2, 16);
    assert.deepEqual([await toggle.getAttribute("aria-expanded"), (await box(toggle)).x, (await box(toggle.locator("svg"))).x, (await box(toggle)).height], ["true", 36, 42, 28]);
    const lead = await page.locator("[data-viewer-navbar]").evaluate((bar) => [...bar.querySelectorAll('[data-navbar-panel="left"], [data-navbar-logo], h1')]
      .map((node) => node.getAttribute("data-navbar-panel") ?? node.getAttribute("data-navbar-logo") ?? node.textContent));
    assert.deepEqual(lead, ["home", "left"]);
    // The navbar's row over it is the row over a file: its own 8px a side, on no centred column.
    assert.deepEqual(await style(page.locator("[data-viewer-navbar]"), "paddingLeft", "paddingRight"), ["8px", "8px"]);
    // Its rows are the panel's rows, 28px, their glyph on the 16px inset, in the home's body size (13/20, not the panel's
    // 12/16: a page's navigation, as Figma's and Drive's sidebars are their body size), its heading too; no count
    // (Figma's and Drive's sidebars have none): Starred is its name alone, with lucide's star.
    const pinned = sidebar.locator('[data-place="pinned"]');
    assert.deepEqual([(await box(pinned)).height, ...(await style(pinned, "fontSize", "lineHeight")), await pinned.textContent()], [28, "13px", "20px", "Starred"]);
    assert.deepEqual(await style(sidebar.locator("h2"), "fontSize", "lineHeight", "fontWeight"), ["13px", "20px", "400"]);
    assert.equal((await box(pinned.locator("svg.lucide-star"))).x, 16);
    // The place on screen is marked as an open tab is: the accent fill at medium weight.
    const recents = sidebar.locator('[data-place="recents"]');
    assert.deepEqual([await recents.getAttribute("aria-current"), ...(await style(recents, "backgroundColor", "fontWeight"))], ["page", await token(page, "--accent"), "500"]);
    assert.deepEqual(await style(pinned, "backgroundColor", "fontWeight"), ["rgba(0, 0, 0, 0)", "400"]);
    // A project whose folder is gone is muted.
    assert.equal((await style(sidebar.locator('[data-place="project:lamp"]'), "color"))[0], await token(page, "--muted-foreground"));
    // The place: its title the page's h1 and its one larger text (the heading step at medium weight), in one row the
    // control tall on the panel's inset (16px) from the sidebar and under the navbar, Sort and the layout at its right
    // end, centred on the title, every control the scale's 28px.
    const title = page.locator("[data-library-title]");
    assert.deepEqual([await title.evaluate((node) => node.tagName), await title.textContent(), ...(await style(title, "fontSize", "lineHeight", "fontWeight"))], ["H1", "Recents", "15px", "20px", "500"]);
    const head = await box(page.locator("[data-library-head]"));
    assert.deepEqual([head.x, head.y, head.right, head.height], [232 + 16, navbar.bottom + 16, 1440 - 16, 28]);
    // One row: Sort and the layout are in it, not under it, their vertical centres on the title's.
    const toolbar = await box(page.locator("[data-library-toolbar]"));
    assert.deepEqual([toolbar.right, toolbar.height, toolbar.y >= head.y, toolbar.bottom <= head.bottom], [1440 - 16, 28, true, true]);
    for (const name of ["Sort by Last activity", "Grid", "List"]) assert.equal((await box(page.getByRole("button", { name }))).height, 28, name);
    const middle = async (locator) => { const { y, height } = await box(locator); return y + height / 2; };
    for (const name of ["Sort by Last activity", "Grid", "List"]) assert.ok(Math.abs(await middle(page.getByRole("button", { name })) - await middle(title)) <= 1, `${name} is centred on the title`);
    assert.equal(Math.round((await box(page.getByRole("button", { name: "List" }))).right), 1440 - 16);
    // Grid and list are one segmented control: a 28px track on the muted fill, each option's face 2px in, the chosen one
    // raised on the page's colour.
    const layout = page.getByRole("group", { name: "Layout" });
    const faces = await page.locator("[data-segment] > span").evaluateAll((nodes) => nodes.map((node) => {
      const { width, height } = node.getBoundingClientRect(); return [Math.round(width), Math.round(height), getComputedStyle(node).backgroundColor]; }));
    assert.deepEqual([(await box(layout)).height, (await box(layout)).width, ...(await style(layout, "backgroundColor"))], [28, 64, await token(page, "--muted")]);
    assert.deepEqual(faces, [[28, 24, await token(page, "--background")], [28, 24, "rgba(0, 0, 0, 0)"]]);
    // No kind tabs: nothing between the title and the controls, and the cards start 16px under the head.
    assert.deepEqual([await page.getByRole("group", { name: "Show" }).count(), await page.locator("[data-library-kinds]").count(), await page.getByRole("button", { name: "Drawings", exact: true }).count()], [0, 0, 0]);
    assert.equal((await box(page.locator(".cad-library-card").first())).y, head.bottom + 16);
    // Cards at least 200px a column, filling the place's width: five across beside the sidebar at 1440px.
    const cards = await page.locator(".cad-library-card").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect()).map(({ x, width }) => [x, width]));
    assert.deepEqual([cards.every(([, width]) => width >= 200), new Set(cards.slice(0, 5).map(([x]) => x)).size], [true, 5], "every card at least 200px, five across");
    assert.equal(cards[0][0], 232 + 16);
    // A card's line is its activity alone, as Figma's: no project before it.
    assert.match(await page.getByRole("link", { name: "Open housing.xbf", exact: true }).locator("[data-library-status]").textContent(), /^(Viewed|Edited) \d+h ago$/);
  } finally { await context.close(); }
});

test("a card and a place are real links: a plain click stays in this view, and ⌘ or Ctrl and a click opens a new tab at the address", async () => {
  const { context, page } = await home();
  try {
    const card = page.getByRole("link", { name: "Open housing.xbf", exact: true });
    assert.equal(await card.getAttribute("href"), "/id-housing.xbf");
    const [tab] = await Promise.all([context.waitForEvent("page"), card.click({ modifiers: ["ControlOrMeta"] })]);
    assert.equal(tab.url(), `${origin}/id-housing.xbf`);
    await tab.close();
    // A place too; and this view has not moved.
    const project = page.locator('[data-place="project:gearbox"]');
    const [other] = await Promise.all([context.waitForEvent("page"), project.click({ modifiers: ["ControlOrMeta"] })]);
    assert.equal(other.url(), `${origin}/?place=gearbox`);
    await other.close();
    assert.deepEqual([page.url(), await page.locator("[data-library-title]").textContent()], [`${origin}/?`, "Recents"]);
    // A plain click shows the place here: no navigation of the page, its row the marked one.
    await project.click();
    await page.locator('[data-library-title]:text-is("gearbox")').waitFor();
    assert.deepEqual([page.url(), await project.getAttribute("aria-current"), context.pages().length], [`${origin}/?`, "page", 1]);
    // Its page: its folders first, each a link to its own page, a tile of the cards' family (a card's box: its 1px
    // border round a card's 12px inset round one line, 46px) in the cards' columns, then its files: the cards, then the
    // tiles of the files the viewer does not open, in the same columns.
    const folder = page.getByRole("link", { name: "Open dxf", exact: true });
    assert.equal(await folder.getAttribute("href"), "/?place=gearbox&path=dxf");
    const across = (selector) => page.locator(selector).evaluateAll((nodes) => nodes.map((node) => { const { x, width, height } = node.getBoundingClientRect(); return [x, width, height]; }));
    const [tiles, cards, others] = [await across("[data-library-folders] > li"), await across("[data-library-all] .cad-library-card"), await across("[data-library-other-files] > li")];
    assert.deepEqual([tiles.length, tiles.every(([, , height]) => height === 46)], [3, true]);
    const columns = (boxes) => boxes.slice(0, 3).map(([x, width]) => [x, width]);
    assert.deepEqual([columns(tiles).slice(0, cards.length), columns(tiles)], [columns(cards), columns(others)]);
    const [folderTab] = await Promise.all([context.waitForEvent("page"), folder.click({ modifiers: ["ControlOrMeta"] })]);
    assert.equal(folderTab.url(), `${origin}/?place=gearbox&path=dxf`);
    await folderTab.close();
    // A plain click goes into it here; a file of it no page has opened is a link as the rest are; the path leads back up.
    await folder.click();
    await page.locator('[data-library-title]:text-is("dxf")').waitFor();
    assert.equal(await page.getByRole("link", { name: "Open plate_0.dxf" }).getAttribute("href"), "/id-plate_0.dxf");
    const up = page.locator("[data-library-crumb]");
    assert.deepEqual([await up.textContent(), await up.getAttribute("href"), page.url()], ["gearbox", "/?place=gearbox", `${origin}/?`]);
    await up.click();
    await page.locator('[data-library-title]:text-is("gearbox")').waitFor();
    // The keyboard: Up and Down walk the places, and Enter on one goes there.
    await project.focus();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-place")), "recents");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await page.locator('[data-library-title]:text-is("Starred")').waitFor();
    assert.equal(page.url(), `${origin}/?`);
  } finally { await context.close(); }
});

test("the document just left is ringed in the brand's colour and in view, with the way back in the title row, as a card and as a row", async () => {
  for (const layout of ["grid", "list"]) {
    // A window too short for the whole place: the one just left is scrolled to.
    const { context, page } = await home(`place=gearbox&path=dxf&from=plate_8.dxf&layout=${layout}`, { width: 1100, height: 420 });
    try {
      const ringed = page.locator("[data-from]");
      await ringed.waitFor();
      assert.equal(await ringed.count(), 1);
      assert.equal(await ringed.locator(".cad-library-open").getAttribute("aria-label"), "Open plate_8.dxf");
      const brand = await token(page, "--brand");
      const shadow = (await style(layout === "grid" ? ringed : ringed.locator(".cad-library-open"), "boxShadow"))[0];
      assert.ok(shadow.includes(`${brand} 0px 0px 0px 2px`), `a 2px ring in the brand's colour: ${shadow}`);
      const place = await box(page.locator("[data-library-content]"));
      await page.waitForFunction(() => { const { top, bottom } = document.querySelector("[data-from]").getBoundingClientRect(); return top >= 40 && bottom <= innerHeight; });
      const at = await box(ringed);
      assert.ok(at.y >= place.y && at.bottom <= place.bottom, "the ringed document is in view");
      // The way back in the title row, before Sort and the layout, which end on the place's right line.
      const back = page.getByRole("button", { name: "Back to plate_8.dxf" });
      assert.deepEqual([await back.locator("kbd").textContent(), await back.evaluate((node) => Boolean(node.closest("[data-library-head]"))),
        (await box(back)).right <= (await box(page.getByRole("button", { name: "Sort by Last activity" }))).x, Math.round((await box(page.getByRole("button", { name: "List" }))).right)],
        ["Esc", true, true, Math.round(await page.locator("[data-library-content]").evaluate((node) => node.getBoundingClientRect().left + node.clientWidth - 16))]);
    } finally { await context.close(); }
  }
});

test("a home too narrow for its sidebar collapses it and keeps its title; at a phone's width every control is a finger's", async () => {
  // A pane 700px wide in a wider window: the home measures itself, never the window.
  const pane = await home("width=700", { width: 1300, height: 800 });
  try {
    const { page } = pane;
    // Collapsed by its width, nothing of it left: the place from the pane's edge, on the narrow gutters.
    assert.equal(await page.getByRole("navigation", { name: "Places" }).count(), 0);
    assert.equal(await page.locator('[data-viewer-navbar] [data-navbar-panel="left"]').getAttribute("aria-expanded"), "false");
    assert.deepEqual([(await box(page.locator("[data-library-content]"))).x, (await box(page.locator("[data-library-title]"))).x], [0, 16]);
    // No menu of places on the title, and no name in the navbar: the place's title, the page's one h1, in its own row.
    assert.deepEqual([await page.locator("[data-viewer-navbar] h1").count(), await page.locator("h1").textContent(),
      await page.getByRole("button", { name: /^Places/ }).count()], [0, "Recents", 0]);
  } finally { await pane.context.close(); }
  const phone = await home("place=gearbox&from=housing", { width: 390, height: 844 });
  try {
    const { page } = phone;
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    // The scale's switch eases a button's size: measured once nothing is moving.
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    assert.equal(await page.getByRole("navigation", { name: "Places" }).count(), 0);
    // The phone's scale: 36px controls, each text 2px up; the place on 16px gutters, one card across.
    for (const name of ["Show panel", "Home", "Grid", "List", "Sort by Last activity", "Back to housing", "Import", "Search models"]) {
      assert.equal((await box(page.getByRole(name === "Home" ? "link" : "button", { name }).first())).height, 36, name);
    }
    assert.deepEqual(await style(page.locator("[data-library-title]"), "fontSize", "lineHeight", "fontWeight"), ["17px", "22px", "500"]);
    const cards = await page.locator(".cad-library-card").evaluateAll((nodes) => nodes.slice(0, 2).map((node) => { const { x, width } = node.getBoundingClientRect(); return [x, width]; }));
    assert.deepEqual(cards, [[16, 358], [16, 358]]);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "nothing wider than the phone");
    // Import is its icon alone there, still named.
    assert.equal((await box(page.getByRole("button", { name: "Import" }))).width, 36);
  } finally { await phone.context.close(); }
});

// The sidebar is the viewer's panel over the home (`docs/viewer-ux.md`, "The panel"): the same toggle, peek, key, grip and sheet.
const SIDEBAR = "aside[data-library-sidebar]";
const TOGGLE = '[data-viewer-navbar] [data-navbar-panel="left"]';
const still = (page) => page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
const kept = (page) => page.evaluate(() => window.homePanel ?? null);

test("the home's sidebar pushes the place while pinned and leaves nothing collapsed; its width follows the home until the person chooses", async () => {
  const { context, page } = await home();
  try {
    const content = page.locator("[data-library-content]");
    assert.deepEqual([(await box(content)).x, (await box(page.locator("[data-library-title]"))).x], [232, 248]);
    // Narrower than 872px (640 for the place beside the default 232) it collapses by itself, and opens again past it; nothing is kept.
    await page.setViewportSize({ width: 871, height: 900 });
    await page.locator(SIDEBAR).waitFor({ state: "hidden" });
    assert.deepEqual([(await box(content)).x, (await box(content)).width, await page.locator(TOGGLE).getAttribute("aria-expanded")], [0, 871, "false"]);
    await page.setViewportSize({ width: 872, height: 900 });
    await page.locator(SIDEBAR).waitFor({ state: "visible" });
    assert.deepEqual([(await box(content)).x, await kept(page)], [232, null]);
    // The toggle collapses it: the place takes the whole width, and that choice holds however wide the window.
    await page.locator(TOGGLE).click();
    await page.locator(SIDEBAR).waitFor({ state: "hidden" });
    await page.mouse.move(700, 500);
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.waitForFunction(() => document.querySelector("[data-library-content]").getBoundingClientRect().width === 1600);
    assert.deepEqual([(await box(content)).x, await page.locator(SIDEBAR).isVisible(), await kept(page)], [0, false, { open: false }]);
    // Its key (Ctrl+\ off a Mac) opens it again, their choice too, and it then holds in a narrow window.
    await page.keyboard.press("Control+Backslash");
    await page.locator(SIDEBAR).waitFor({ state: "visible" });
    await page.setViewportSize({ width: 700, height: 900 });
    await page.waitForFunction(() => document.querySelector("[data-library-content]").getBoundingClientRect().width === 700 - 232);
    assert.deepEqual([(await box(content)).x, await kept(page)], [232, { open: true }]);
  } finally { await context.close(); }
});

test("resting on the toggle peeks the collapsed sidebar as a card over the place, 4px in, pushing nothing; it goes when left, and the toggle pins it", async () => {
  const { context, page } = await home('panel={"open":false}');
  try {
    const navbar = await box(page.locator("[data-viewer-navbar]"));
    const content = page.locator("[data-library-content]");
    assert.deepEqual([await page.locator(SIDEBAR).isVisible(), (await box(content)).x], [false, 0]);
    await page.locator(TOGGLE).hover();
    await page.locator(`${SIDEBAR}[data-panel-peek]`).waitFor();
    await still(page);
    // A card on the panel's surface, 4px in from the window's left, the navbar and the bottom, at the panel's width.
    const card = await box(page.locator(`${SIDEBAR} [data-panel-peek-card]`));
    assert.deepEqual([card.x, card.y, card.right, card.bottom], [4, navbar.bottom + 4, 232 - 4, 900 - 4]);
    assert.deepEqual(await style(page.locator(`${SIDEBAR} [data-panel-peek-card]`), "backgroundColor", "borderTopLeftRadius"), [await token(page, "--sidebar"), "10px"]);
    // Over the place, which has not moved; the toggle still says collapsed, and its hint is gone.
    assert.deepEqual([(await box(content)).x, await page.locator(TOGGLE).getAttribute("aria-expanded"), await page.getByRole("tooltip").count()], [0, "false", 0]);
    // Its rows stand where a pinned sidebar's do, and the foot (the links, Settings) is at its bottom, inside the card.
    assert.equal((await box(page.locator(`${SIDEBAR} [data-place="pinned"] svg`))).x, 16);
    const cog = await box(page.locator(`${SIDEBAR} [data-app-foot]`).getByRole("button", { name: "Settings" }));
    assert.deepEqual([cog.bottom, cog.right <= card.right], [900 - 8, true]);
    // From the toggle into the card it stays; a place chosen in it is shown without pinning it.
    await page.locator(`${SIDEBAR} [data-place="pinned"]`).click();
    await page.locator('[data-library-title]:text-is("Starred")').waitFor();
    assert.deepEqual([await page.locator(`${SIDEBAR}[data-panel-peek]`).count(), await kept(page)], [1, null]);
    // Left, it goes; Escape puts it away too.
    await page.mouse.move(900, 500);
    await page.locator(SIDEBAR).waitFor({ state: "hidden" });
    await page.locator(TOGGLE).hover();
    await page.locator(`${SIDEBAR}[data-panel-peek]`).waitFor();
    await page.keyboard.press("Escape");
    await page.locator(SIDEBAR).waitFor({ state: "hidden" });
    // A click on the toggle while it peeks pins it where it stands: the place moves aside, and that is kept.
    await page.mouse.move(900, 500);
    await page.locator(TOGGLE).hover();
    await page.locator(`${SIDEBAR}[data-panel-peek]`).waitFor();
    await page.locator(TOGGLE).click();
    await page.waitForFunction(() => document.querySelector("[data-library-content]").getBoundingClientRect().x === 232);
    assert.deepEqual([await page.locator(`${SIDEBAR}[data-panel-peek]`).count(), await page.locator(TOGGLE).getAttribute("aria-expanded"), await kept(page)], [0, "true", { open: true }]);
  } finally { await context.close(); }
});

test("the sidebar's grip sets its width between 200 and 480px, the place taking the rest, and a kept width is drawn again", async () => {
  const { context, page } = await home();
  try {
    const grip = page.locator(`${SIDEBAR} [data-panel-grip]`);
    const at = await box(grip);
    const y = at.y + 200, x = at.x + at.width / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 100, y, { steps: 4 });
    assert.deepEqual([(await box(page.locator(SIDEBAR))).width, (await box(page.locator("[data-library-content]"))).x, await kept(page)], [332, 332, null]);
    // Past its bounds it stops; it is written once, as the drag lets go.
    await page.mouse.move(x + 900, y, { steps: 4 });
    assert.equal((await box(page.locator(SIDEBAR))).width, 480);
    await page.mouse.move(x - 500, y, { steps: 4 });
    assert.equal((await box(page.locator(SIDEBAR))).width, 200);
    await page.mouse.move(x + 68, y, { steps: 4 });
    await page.mouse.up();
    assert.deepEqual([(await box(page.locator(SIDEBAR))).width, await kept(page)], [300, { width: 300 }]);
  } finally { await context.close(); }
  const again = await home('panel={"width":300}');
  try {
    assert.deepEqual([(await box(again.page.locator(SIDEBAR))).width, (await box(again.page.locator("[data-library-content]"))).x], [300, 300]);
  } finally { await again.context.close(); }
});

test("the sidebar ends in the panel's foot under a full-width rule: the host's links as icon tiles at its left, Settings' cog at its right corner, its menu opening upward", async () => {
  const { context, page } = await home("", { width: 1440, height: 420 });
  try {
    const side = await box(page.locator(SIDEBAR));
    const foot = page.locator(`${SIDEBAR} [data-app-foot]`);
    const at = await box(foot);
    // Pinned at the sidebar's bottom, its rule a hairline in the border's colour from edge to edge (to the sidebar's own right rule).
    assert.deepEqual([at.x, at.right, at.bottom], [0, 232 - 1, side.bottom]);
    assert.deepEqual(await style(foot, "borderTopWidth", "borderTopColor"), ["1px", await token(page, "--border")]);
    // The tiles: the links in their order, then the cog; each the control's 28px, 8px under the rule and over the bottom.
    const tiles = foot.locator("a, button");
    assert.deepEqual(await tiles.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("aria-label"))), ["GitHub", "Discord", "Send feedback", "Settings"]);
    const boxes = await tiles.evaluateAll((nodes) => nodes.map((node) => { const { x, y, width, height, right, bottom } = node.getBoundingClientRect(); return { x, y, width, height, right, bottom }; }));
    assert.deepEqual(boxes.map(({ width, height, y, bottom }) => [width, height, y, bottom]), boxes.map(() => [28, 28, at.y + 1 + 8, side.bottom - 8]));
    // The first glyph and the cog's stand on the panel's two lines, 16px in; the cog at the right corner, apart.
    const glyphs = await foot.locator("svg").evaluateAll((nodes) => nodes.map((node) => { const { x, right, width } = node.getBoundingClientRect(); return { x, right, width }; }));
    assert.deepEqual([glyphs[0].x, glyphs.at(-1).right, glyphs.every(({ width }) => width === 14)], [16, 232 - 1 - 16, true]);
    assert.ok(boxes[3].x - boxes[2].right > 28, "the cog stands apart, at the right");
    // Muted at rest, the foreground under the pointer, its name in a hint over it.
    const github = foot.getByRole("link", { name: "GitHub" });
    assert.equal((await style(github, "color"))[0], await token(page, "--muted-foreground"));
    await github.hover();
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    assert.deepEqual([(await style(github, "color"))[0], await page.getByRole("tooltip").textContent()], [await token(page, "--foreground"), "GitHub"]);
    assert.ok((await box(page.getByRole("tooltip"))).bottom <= at.y + 9, "the hint stands over its tile");
    // A press follows the link the host's way; the page stays.
    await github.click();
    await foot.getByRole("link", { name: "Send feedback" }).click();
    const opened = await page.evaluate(() => window.homeOpened);
    assert.deepEqual([opened[0], opened[1].split("?")[0], context.pages().length], ["https://github.com/example/cad", "https://github.com/earthtojake/text-to-cad/issues/new", 1]);
    // The places scroll over the foot; it does not move, and they end at its rule.
    await page.locator(`${SIDEBAR} [data-panel-scroller]`).evaluate((node) => { node.scrollTop = node.scrollHeight; });
    assert.deepEqual([(await box(foot)).y, (await box(page.locator(`${SIDEBAR} [data-slot="scroll-area"]`))).bottom], [at.y, at.y]);
    // The cog opens what is left of the app's menu, upward: the person's settings and the version; no links in it.
    const cog = foot.getByRole("button", { name: "Settings" });
    await cog.click();
    const menu = page.getByRole("menu", { name: "Settings" });
    await menu.waitFor();
    await still(page);
    const shown = await box(menu);
    assert.ok(shown.bottom <= boxes[3].y && shown.y >= 0 && shown.x >= 0, `the menu stands over the cog: ${JSON.stringify(shown)}`);
    assert.deepEqual([await menu.getAttribute("data-side"), await cog.getAttribute("aria-expanded"), (await style(cog, "backgroundColor"))[0]], ["top", "true", await token(page, "--accent")]);
    assert.deepEqual(await menu.locator('[role^="menuitem"]').evaluateAll((items) => items.map((item) => item.textContent || item.getAttribute("aria-label"))),
      ["Telemetry", "System", "Light", "Dark"]);
    assert.match(await menu.locator("[data-menu-footer]").textContent(), /^v0\.7\.4/);
    // A setting turns without closing it; Escape closes it, the focus back on the cog.
    await menu.getByRole("menuitemcheckbox", { name: "Telemetry" }).click();
    assert.equal(await menu.getByRole("menuitemcheckbox", { name: "Telemetry" }).getAttribute("aria-checked"), "true");
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "detached" });
    // The menu gives the focus back a task after it unmounts: awaited, never read at once.
    await page.waitForFunction((node) => node === document.activeElement, await cog.elementHandle());
  } finally { await context.close(); }
  // At the sidebar's narrowest, 200px, the row still fits on one line, the cog in its corner.
  const narrow = await home('panel={"width":200}');
  try {
    const foot = narrow.page.locator(`${SIDEBAR} [data-app-foot]`);
    const boxes = await foot.locator("a, button").evaluateAll((nodes) => nodes.map((node) => { const { y, right } = node.getBoundingClientRect(); return { y, right }; }));
    assert.deepEqual([new Set(boxes.map(({ y }) => y)).size, boxes.at(-1).right, await foot.evaluate((node) => node.scrollWidth <= node.clientWidth)], [1, 200 - 1 - 9, true]);
  } finally { await narrow.context.close(); }
});

test("on a phone the sidebar is the panel's sheet under the navbar, ending in the panel's foot; a place chosen in it closes it", async () => {
  // A finger's phone: every press here is a tap.
  const { context, page } = await home("", { width: 390, height: 844 }, { hasTouch: true });
  try {
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    await still(page);
    const navbar = await box(page.locator("[data-viewer-navbar]"));
    const sheet = page.locator("[data-panel-sheet]");
    assert.deepEqual([await sheet.count(), await page.locator(SIDEBAR).count(), await page.locator(TOGGLE).getAttribute("aria-expanded")], [0, 0, "false"]);
    await page.locator(TOGGLE).tap();
    await sheet.waitFor();
    await still(page);
    // From the left under the navbar, 85% of the width and 20rem at most, to the bottom; no scrim; the navbar still in reach.
    const at = await box(sheet);
    assert.deepEqual([at.x, at.y, at.width, at.bottom], [0, navbar.bottom, 320, 844]);
    assert.deepEqual([(await style(page.locator('[data-slot="sheet-overlay"]'), "backgroundColor"))[0], await page.locator(TOGGLE).getAttribute("aria-expanded")], ["rgba(0, 0, 0, 0)", "true"]);
    // The same places at a finger's size, and the foot at its bottom under its rule: the links and the cog, each a
    // finger's 36px, the cog's menu over it.
    assert.equal((await box(sheet.locator('[data-place="pinned"]'))).height, 36);
    const foot = sheet.locator("[data-app-foot]");
    assert.deepEqual([(await box(foot)).x, (await box(foot)).right, (await box(foot)).bottom, (await style(foot, "borderTopWidth"))[0]], [0, 320 - 1, 844, "1px"]);
    assert.deepEqual(await foot.locator("a, button").evaluateAll((nodes) => nodes.map((node) => [node.getAttribute("aria-label"), node.getBoundingClientRect().height])),
      [["GitHub", 36], ["Discord", 36], ["Send feedback", 36], ["Settings", 36]]);
    const row = foot.getByRole("button", { name: "Settings" });
    assert.deepEqual([(await box(row)).height, (await box(row)).bottom], [36, 844 - 8]);
    await row.tap();
    const menu = page.getByRole("menu", { name: "Settings" });
    await menu.waitFor();
    // What iOS does next: the tapped row takes focus, at the tap's click; the menu a tap opened stays open.
    await row.evaluate((node) => node.focus());
    await still(page);
    assert.equal(await row.getAttribute("data-state"), "open", "still open once its cog has focus");
    assert.ok((await box(menu)).bottom <= (await box(row)).y, "the menu opens upward");
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "detached" });
    assert.equal(await sheet.count(), 1, "Escape closed the menu, not the sheet under it");
    // A place chosen is shown, and the sheet gives the page back; the toggle shuts it too, and nothing was kept.
    await sheet.locator('[data-place="project:gearbox"]').tap();
    await sheet.waitFor({ state: "detached" });
    assert.equal(await page.locator("[data-library-title]").textContent(), "gearbox");
    await page.locator(TOGGLE).tap();
    await sheet.waitFor();
    await page.locator(TOGGLE).tap();
    await sheet.waitFor({ state: "detached" });
    // A tap beside the sheet closes it too, and leaves the page as it was.
    await page.locator(TOGGLE).tap();
    await sheet.waitFor();
    await page.touchscreen.tap(360, 600);
    await sheet.waitFor({ state: "detached" });
    assert.equal(await page.locator("[data-library-title]").textContent(), "gearbox");
    assert.equal(await kept(page), null);
  } finally { await context.close(); }
});

test("the navbar's logo is a link home: a plain click shows Recents in this view, ⌘ or Ctrl and a click opens the home in a new tab, and its hint says Home", async () => {
  const { context, page } = await home("place=gearbox");
  try {
    const logo = page.getByRole("link", { name: "Home" });
    assert.deepEqual([await logo.getAttribute("href"), await logo.evaluate((node) => Boolean(node.closest("[data-viewer-navbar]"))), (await box(logo)).height], ["/?place=recents", true, 28]);
    await logo.hover();
    assert.equal(await page.getByRole("tooltip").textContent(), "Home");
    const [tab] = await Promise.all([context.waitForEvent("page"), logo.click({ modifiers: ["ControlOrMeta"] })]);
    assert.equal(tab.url(), `${origin}/?place=recents`);
    await tab.close();
    assert.equal(await page.locator("[data-library-title]").textContent(), "gearbox");
    // A plain click: Recents here, with no navigation of the page, and no menu.
    await logo.click();
    await page.locator('[data-library-title]:text-is("Recents")').waitFor();
    assert.deepEqual([page.url(), await page.getByRole("menu").count(), context.pages().length], [`${origin}/?place=gearbox`, 0, 1]);
  } finally { await context.close(); }
  // A host with no addresses (an app's frame): the same logo, a button.
  const framed = await home("place=gearbox&links=0");
  try {
    assert.equal(await framed.page.getByRole("link", { name: "Home" }).count(), 0);
    await framed.page.getByRole("button", { name: "Home" }).click();
    await framed.page.locator('[data-library-title]:text-is("Recents")').waitFor();
  } finally { await framed.context.close(); }
});

test("a menu stands 6px from its trigger and is padded 6px, its items on the row", async () => {
  const { context, page } = await home();
  try {
    const trigger = page.getByRole("button", { name: "Sort by Last activity" });
    await trigger.click();
    const menu = page.getByRole("menu", { name: "Sort" });
    await menu.waitFor();
    // Measured once it has stopped zooming in.
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    const [above, under] = [await box(trigger), await box(menu)];
    assert.equal(Math.round(under.y - above.bottom), 6, "6px under its trigger");
    assert.deepEqual(await style(menu, "paddingTop", "paddingLeft"), ["6px", "6px"]);
    const item = await box(menu.getByRole("menuitemradio").first());
    assert.deepEqual([Math.round(item.x - under.x), Math.round(item.y - under.y), item.height], [7, 7, 28], "6px in from inside its 1px edge, the row tall");
  } finally { await context.close(); }
});

// The head is one row at every width: the title (or the path) truncates first, and where the controls still do not fit
// Sort is its glyph alone, keeping its accessible name and its menu. Measured from what is drawn.
const LONG = "place=gearbox&path=" + encodeURIComponent("housing/v3/drawings/assembly instructions for the second production batch");
async function oneRow(page, label) {
  const middle = async (locator) => { const { y, height } = await box(locator); return y + height / 2; };
  const head = await box(page.locator("[data-library-head]"));
  const sort = page.getByRole("button", { name: /^Sort by / });
  const title = page.locator("[data-library-title]");
  assert.ok(Math.abs(await middle(sort) - await middle(title)) <= 1, `${label}: Sort is centred on the title`);
  const controls = [sort, page.getByRole("button", { name: "Grid" }), page.getByRole("button", { name: "List" })];
  for (const control of controls) assert.ok(Math.abs(await middle(control) - await middle(title)) <= 1, `${label}: ${await control.getAttribute("aria-label")} is centred on the title`);
  const bottoms = await Promise.all([title, ...controls].map(async (control) => (await box(control)).bottom));
  assert.ok(bottoms.every((bottom) => bottom <= head.bottom + 1), `${label}: one row, nothing under the head`);
  assert.ok((await box(controls[2])).right <= head.right + 1, `${label}: the layout switch ends inside the place's right line`);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${label}: nothing wider than the window`);
  return { sort, title, head };
}
// Whether Sort's name and chevron are drawn: a box with a width.
const drawn = (sort) => sort.evaluate((node) => [...node.children].map((child) => child.getBoundingClientRect().width > 0));

test("the head stays one row on a narrow page and at a phone's width: the title truncates first, then Sort is its glyph alone, still named and with its menu", async () => {
  // A wide place: Sort says its name; the way back, the title and the controls are one row.
  const wide = await home(LONG);
  try {
    const { sort } = await oneRow(wide.page, "wide");
    assert.deepEqual(await drawn(sort), [true, true, true]);
  } finally { await wide.context.close(); }
  // A narrow page (its own width, not the window's) and a phone, each with a path too long for the row; and the
  // narrowest page, with a short title.
  for (const [label, query, viewport, long] of [["a 320px pane", `${LONG}&width=320`, { width: 800, height: 800 }, true], ["a phone", LONG, { width: 390, height: 844 }, true],
    ["a phone with the way back", "place=gearbox&from=housing", { width: 390, height: 844 }, false], ["a 240px pane", "width=240", { width: 800, height: 800 }, false]]) {
    const { context, page } = await home(query, viewport);
    try {
      await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
      const { sort, title } = await oneRow(page, label);
      assert.ok((await box(title)).width > 0, `${label}: the title is still there`);
      // The title gave way first: where it is a long path it is cut, its text wider than its box.
      if (long) assert.equal(await page.locator("[data-library-crumbs]").evaluate((node) => node.scrollWidth > node.clientWidth || [...node.querySelectorAll("a, button, h1")].some((part) => part.scrollWidth > part.clientWidth)), true, `${label}: the path is cut`);
      // Sort is its glyph alone: the name and the chevron are not drawn; its accessible name and its menu stay.
      assert.deepEqual(await drawn(sort), [true, false, false], label);
      assert.equal((await box(sort)).height, await page.evaluate(() => { const probe = document.createElement("i"); probe.style.height = "var(--cad-control)"; document.querySelector("[data-library-head]").append(probe); const { height } = probe.getBoundingClientRect(); probe.remove(); return height; }), `${label}: the control tall`);
      assert.equal(await sort.getAttribute("aria-label"), "Sort by Last activity");
      await sort.click();
      const menu = page.getByRole("menu", { name: "Sort" });
      assert.deepEqual(await menu.getByRole("menuitemradio").allTextContents(), ["Last activity", "Name", "Last viewed", "Last edited"], label);
      await page.keyboard.press("Escape");
      await menu.waitFor({ state: "hidden" });
    } finally { await context.close(); }
  }
  // At a phone's scale every option of the layout and Sort are a finger's, with no kind tabs.
  const phone = await home("", { width: 390, height: 844 });
  try {
    const { page } = phone;
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    await oneRow(page, "Recents on a phone");
    for (const name of ["Sort by Last activity", "Grid", "List"]) assert.equal((await box(page.getByRole("button", { name, exact: true }))).height, 36, name);
    assert.equal(await page.getByRole("group", { name: "Show" }).count(), 0);
    assert.deepEqual(await page.locator("[data-segment] > span").evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().height))), [32, 32]);
  } finally { await phone.context.close(); }
});

test("Import is one button opening the system's chooser where it takes a file or a folder, else a menu of File… and Folder…; the + by Projects is the folder chooser", async () => {
  // Where the system's chooser takes either (a Mac's, as VS Code's "Open…" is there): one button, its icon and its word
  // with no chevron, padded alike at both ends, the control tall; a press opens that chooser, and no menu.
  const one = await home("chooser=one");
  try {
    const { page } = one;
    const button = page.getByRole("button", { name: "Import", exact: true });
    const [at, icon, word] = [await box(button), await box(button.locator("svg")), await box(button.locator("span"))];
    assert.deepEqual([await button.locator("svg").count(), at.height, ...(await style(button, "paddingLeft", "paddingRight")), icon.x - at.x, Math.round(at.right - word.right),
      await button.getAttribute("aria-haspopup")], [1, 28, "8px", "8px", 9, 9, null]);
    await button.click();
    await page.waitForFunction(() => window.homeChoosers?.length === 1);
    assert.deepEqual([await page.evaluate(() => window.homeChoosers), await page.getByRole("menu").count()], [["any"], 0]);
    // The + by Projects is the folder chooser there too.
    await page.getByRole("button", { name: "Open a folder as a project" }).click();
    await page.waitForFunction(() => window.homeChoosers?.length === 2);
    assert.deepEqual(await page.evaluate(() => window.homeChoosers), ["any", "folder"]);
  } finally { await one.context.close(); }
  // Where it does not (Windows', Linux's): a menu of File… and Folder…, a dropdown's chevron after the word.
  const two = await home();
  try {
    const { page } = two;
    const button = page.getByRole("button", { name: "Import", exact: true });
    assert.deepEqual([await button.locator("svg").count(), await button.getAttribute("aria-haspopup")], [2, "menu"]);
    await button.click();
    const menu = page.getByRole("menu");
    assert.deepEqual(await menu.getByRole("menuitem").allTextContents(), ["File…", "Folder…"]);
    await menu.getByRole("menuitem", { name: "Folder…" }).click();
    await page.waitForFunction(() => window.homeChoosers?.length === 1);
    assert.deepEqual(await page.evaluate(() => window.homeChoosers), ["folder"]);
  } finally { await two.context.close(); }
  // The welcome's ways in are the same: one Import where one chooser takes either, else Import file and Import folder.
  for (const [query, names] of [["state=empty&chooser=one", ["Import"]], ["state=empty", ["Import file", "Import folder"]]]) {
    const { context, page } = await home(query, undefined, { waitFor: "[data-library-empty]" });
    try {
      assert.deepEqual(await page.locator("[data-library-empty]").getByRole("button").allTextContents(), names, query);
    } finally { await context.close(); }
  }
  // In a navbar under 480px (a phone's), the one button is its icon alone, a finger's 36px square, still named.
  const phone = await home("chooser=one", { width: 390, height: 844 });
  try {
    await phone.page.locator('[data-viewer-layout="mobile"]').waitFor();
    await still(phone.page);
    const at = await box(phone.page.getByRole("button", { name: "Import", exact: true }));
    assert.deepEqual([at.width, at.height], [36, 36]);
  } finally { await phone.context.close(); }
});

// What the home is drawn with (`docs/design-system.md`): the spacing scale, the tokens' radii and the type scale's steps,
// read from what is drawn, never from a class.
const px = (locator, ...names) => style(locator, ...names);
const type = async (locator) => (await style(locator.first(), "fontSize", "lineHeight", "fontWeight")).join(" ");

test("the place is padded by the panel's inset on every side, its blocks 16px apart; a card has a card's corners and inset, a folder is a tile of the cards' family, and a list's row is the search's", async () => {
  const { context, page } = await home("place=gearbox");
  try {
    const line = 232 + 16;
    // One inset on all four sides (16px), and the title's glyph, a folder's tile and the first card all on its line.
    assert.deepEqual(await px(page.locator("[data-library-content]"), "paddingTop", "paddingRight", "paddingBottom", "paddingLeft"), ["16px", "16px", "16px", "16px"]);
    // gearbox's top leads with Recent; the listing is under All files.
    const folders = page.locator("[data-library-folders] > li");
    const cards = page.locator("[data-library-all] .cad-library-card");
    assert.deepEqual([(await box(page.locator("[data-library-head] svg").first())).x, (await box(folders.first())).x, (await box(cards.first())).x], [line, line, line]);
    // The content 16px under the head, which is one row: Sort and the layout stand inside it.
    const head = await box(page.locator("[data-library-head]"));
    assert.deepEqual([head.height, (await box(page.locator("[data-library-head] + *"))).y - head.bottom], [28, 16]);
    // A folder: a tile of the cards' family, a card's box and 10px corners in a card's column, a card's 12px inset round
    // its glyph and its name, in a card's 1px border (46px tall), its name a card's name in size and weight, its glyph where a card's name
    // starts; 16px apart and 16px over the cards.
    const folder = folders.first();
    assert.deepEqual([(await box(folder)).height, (await box(folder)).width, ...(await px(folder, "borderTopWidth", "borderTopLeftRadius"))],
      [46, (await box(cards.first())).width, "1px", "10px"]);
    assert.deepEqual([await type(folder.locator("[data-library-label]")), await type(cards.first().locator("[data-library-label]"))], ["13px 20px 500", "13px 20px 500"]);
    assert.equal((await box(folder.locator("svg"))).x, (await box(cards.first().locator("[data-library-label]"))).x);
    assert.equal((await box(cards.first())).y - (await box(folders.first())).bottom, 16);
    // A card: a card's 10px corners, the picture at 3:2 edge to edge, the caption padded by a card's 12px inset all round;
    // 16px between cards, across (here) and down (a folder of more than a row, below).
    const [first, second] = [await box(cards.nth(0)), await box(cards.nth(1))];
    // Columns share the width in fractions of a pixel, so a 3:2 picture's height is fractional too: measured to the pixel.
    assert.deepEqual([Math.round(second.x - first.right), (await px(cards.first(), "borderTopLeftRadius"))[0]], [16, "10px"]);
    const picture = await box(cards.first().locator("[data-library-picture]"));
    assert.deepEqual([picture.width, Math.round(picture.height * 3)], [first.width - 2, Math.round(picture.width * 2)]);
    const caption = cards.first().locator("[data-library-label]").locator("xpath=..");
    assert.deepEqual(await px(caption, "paddingTop", "paddingRight", "paddingBottom", "paddingLeft"), ["12px", "12px", "12px", "12px"]);
    // Its format is the system's chip: the chip tall, 8px in, a row's corners, 8px in from the picture's corner.
    const badge = cards.first().locator("[data-library-format]");
    assert.deepEqual([(await box(badge)).height, (await box(badge)).x - picture.x, (await box(badge)).y - picture.y, ...(await px(badge, "paddingLeft", "borderTopLeftRadius"))], [20, 8, 8, "8px", "8px"]);
    // The type: the title at the heading step's size and medium weight; a card's name medium and its line regular and
    // muted, both the body's size; the chip's own step.
    assert.deepEqual([await type(page.locator("[data-library-title]")), await type(cards.first().locator("[data-library-label]")),
      await type(cards.first().locator("[data-library-status]")), await type(badge)], ["15px 20px 500", "13px 20px 500", "13px 20px 400", "12px 16px 500"]);
    assert.equal((await style(cards.first().locator("[data-library-status]"), "color"))[0], await token(page, "--muted-foreground"));
    // The list: a header of muted labels the control tall, on the line, then rows the control + 16 tall with a row's
    // corners, each picture the control + 4 tall at 3:2 on the line; names and facts one size, told apart by colour.
    await page.getByRole("button", { name: "List" }).click();
    const rows = page.locator("[data-library-all] .cad-library-row");
    await rows.first().waitFor();
    const header = page.locator("[data-library-all] [data-library-columns]");
    assert.deepEqual([(await box(header)).height, (await box(header)).x, await type(header.locator("span")), (await style(header, "borderBottomWidth"))[0]], [28, line, "13px 20px 400", "0px"]);
    // The header names what a card says and nothing else: Name, Type, Last viewed, Last edited, as drawn.
    assert.deepEqual(await header.locator("span").evaluateAll((nodes) => nodes.filter((node) => node.getBoundingClientRect().width > 0).map((node) => node.innerText)), ["Name", "Type", "Last viewed", "Last edited"]);
    // A folder's Type reads "Folder" with a dash for each time; a file no page opened has a dash for Last viewed.
    const cells = (row) => row.locator("[data-column]").evaluateAll((nodes) => nodes.map((node) => node.innerText));
    assert.deepEqual(await cells(rows.filter({ has: page.locator("[data-library-folder-picture]") }).first()), ["Folder", "—", "—"]);
    assert.deepEqual(await cells(rows.filter({ hasText: "bearing-6204-datasheet.pdf" })), ["PDF", "—", await rows.filter({ hasText: "bearing-6204-datasheet.pdf" }).locator('[data-column="edited"]').innerText()]);
    const file = rows.filter({ has: page.locator("[data-library-picture]") }).first();
    const small = await box(file.locator("[data-library-picture]"));
    assert.deepEqual([(await box(file)).height, (await box(file)).x, small.x, small.width, small.height, (await px(file.locator(".cad-library-open"), "borderTopLeftRadius"))[0]], [44, line - 8, line, 48, 32, "8px"]);
    assert.deepEqual([await type(file.locator("[data-library-label]")), await type(file.locator('[data-column="type"]')), (await box(rows.nth(1))).y - (await box(rows.nth(0))).bottom], ["13px 20px 400", "13px 20px 400", 0]);
    assert.deepEqual([(await style(file.locator("[data-library-label]"), "color"))[0], (await style(file.locator('[data-column="type"]'), "color"))[0]], [await token(page, "--foreground"), await token(page, "--muted-foreground")]);
  } finally { await context.close(); }
  // Below the project's top the title is the path, every part at the title's size: the parts above regular and muted
  // (links back up), the slashes regular and muted, the folder on screen medium in the foreground.
  const deep = await home("place=gearbox&path=housing/v3&from=lid.step");
  try {
    const { page } = deep;
    assert.deepEqual([await page.locator("[data-library-crumb]").allTextContents(), await page.locator("[data-library-title]").textContent()], [["gearbox", "housing"], "v3"]);
    const slash = page.locator("[data-library-crumbs] > [aria-hidden]").first();
    assert.deepEqual([await type(page.locator("[data-library-crumb]")), (await style(page.locator("[data-library-crumb]").first(), "color"))[0], await type(slash), (await style(slash, "color"))[0],
      await type(page.locator("[data-library-title]")), (await style(page.locator("[data-library-title]"), "color"))[0]],
    ["15px 20px 400", await token(page, "--muted-foreground"), "15px 20px 400", await token(page, "--muted-foreground"), "15px 20px 500", await token(page, "--foreground")]);
    // The way back: the scale's button, the control tall and 8px in at each side, its key a tiny hint in a hairline box.
    const back = page.getByRole("button", { name: "Back to lid.step" });
    assert.deepEqual([(await box(back)).height, await type(back), ...(await px(back, "paddingLeft", "paddingRight")), await type(back.locator("kbd")), (await style(back.locator("kbd"), "borderTopWidth"))[0]],
      [28, "13px 20px 400", "8px", "8px", "11px 16px 400", "1px"]);
  } finally { await deep.context.close(); }
  // Cards 16px apart down too: the first card of the second row, however many stand across.
  const plates = await home("place=gearbox&path=dxf");
  try {
    const cards = plates.page.locator(".cad-library-card");
    const across = await cards.evaluateAll((nodes) => nodes.findIndex((node) => node.getBoundingClientRect().y > nodes[0].getBoundingClientRect().y));
    assert.ok(across > 0, "more than a row of cards");
    assert.equal(Math.round((await box(cards.nth(across))).y - (await box(cards.nth(0))).bottom), 16);
  } finally { await plates.context.close(); }
  // A place with nothing to list says so in one muted line where its first row would stand, 16px under its title: no
  // Sort or layout, with nothing to order or lay out.
  const bare = await home("place=bare", undefined, { waitFor: "[data-library-state]" });
  try {
    const empty = bare.page.locator("[data-library-state]");
    assert.deepEqual([(await box(empty)).x, (await box(empty)).y - (await box(bare.page.locator("[data-library-head]"))).bottom, await type(empty), (await style(empty, "color", "textAlign")).join(" "),
      await bare.page.locator("[data-library-toolbar]").count()], [232 + 16, 16, "13px 20px 400", `${await token(bare.page, "--muted-foreground")} start`, 0]);
  } finally { await bare.context.close(); }
});

// Every text on the home, as drawn, by what it is: the title's step, the chip's, a key cap's, or the body's.
const texts = (page) => page.evaluate(() => {
  const found = {};
  for (const node of document.querySelectorAll(".cad-library *")) {
    if (![...node.childNodes].some((child) => child.nodeType === 3 && child.textContent.trim()) || !node.getClientRects().length) continue;
    const role = node.closest("kbd") ? "key" : node.closest("[data-library-format]") ? "chip" : node.closest("[data-library-crumbs]") || node.matches("[data-library-title]") ? "title" : "body";
    const { fontSize, lineHeight } = getComputedStyle(node);
    (found[role] ??= new Set()).add(`${fontSize} ${lineHeight}`);
  }
  return Object.fromEntries(Object.entries(found).map(([role, sizes]) => [role, [...sizes].sort()]));
});

test("the home's type is three sizes, as Figma's file browser's: a title, one body size told apart by weight and colour, and a chip's step", async () => {
  const { context, page } = await home("place=gearbox&path=housing/v3&from=lid.step");
  try {
    // The title (the path at a folder of a project), the body everywhere else (the sidebar's rows and heading, the
    // toolbar, the cards, a folder's tile, the way back), the chip on a card's picture, and a key cap's own step.
    assert.deepEqual(await texts(page), { title: ["15px 20px"], body: ["13px 20px"], chip: ["12px 16px"], key: ["11px 16px"] });
    await page.getByRole("button", { name: "List" }).click();
    await page.locator(".cad-library-row").first().waitFor();
    assert.deepEqual(await texts(page), { title: ["15px 20px"], body: ["13px 20px"], key: ["11px 16px"] });
  } finally { await context.close(); }
  // Recents; and the welcome, with nothing yet: its title the body's size at medium weight.
  for (const query of ["", "state=empty"]) {
    const { context: other, page: shown } = await home(query, undefined, { waitFor: query ? "[data-library-empty]" : ".cad-library-card" });
    try {
      assert.deepEqual(await texts(shown), { title: ["15px 20px"], body: ["13px 20px"], ...(query ? {} : { chip: ["12px 16px"] }) }, query || "recents");
      if (query) assert.deepEqual(await style(shown.getByRole("heading", { name: "Nothing here yet" }), "fontSize", "fontWeight"), ["13px", "500"]);
    } finally { await other.close(); }
  }
});

test("Sort is one ghost control: its glyph, the sort's name and a muted chevron, padded alike from its edges, filled as a ghost control is", async () => {
  const { context, page } = await home();
  try {
    const sort = page.getByRole("button", { name: "Sort by Last activity" });
    // No label beside it: the control is the first thing in its group.
    assert.equal(await sort.evaluate((node) => node.previousElementSibling), null);
    // From its box's edges to its first and last drawn mark, the control's padding (8px), the same at both ends.
    const [button, glyph, chevron] = [await box(sort), await box(sort.locator("svg").first()), await box(sort.locator("svg").last())];
    assert.deepEqual([button.height, glyph.x - button.x, button.right - chevron.right, glyph.width, chevron.width], [28, 8, 8, 16, 12]);
    // The glyph and the chevron muted at full strength, the name in the foreground at the body's size.
    const muted = await token(page, "--muted-foreground");
    assert.deepEqual([await style(sort.locator("svg").first(), "color", "opacity"), await style(sort.locator("svg").last(), "color", "opacity"),
      await style(sort.locator("span"), "color", "fontSize", "lineHeight", "fontWeight")], [[muted, "1"], [muted, "1"], [await token(page, "--foreground"), "13px", "20px", "400"]]);
    // Transparent at rest; the accent under the pointer and while its menu is open, as every ghost control.
    assert.equal((await style(sort, "backgroundColor"))[0], "rgba(0, 0, 0, 0)");
    await sort.hover();
    await still(page);
    assert.equal((await style(sort, "backgroundColor"))[0], await token(page, "--accent"));
    await sort.click();
    const menu = page.getByRole("menu", { name: "Sort" });
    await menu.waitFor();
    await page.mouse.move(700, 700);
    await still(page);
    assert.deepEqual([(await style(sort, "backgroundColor"))[0], await menu.getByRole("menuitemradio").evaluateAll((items) => items.map((item) => [item.textContent, item.getAttribute("aria-checked")]))],
      [await token(page, "--accent"), [["Last activity", "true"], ["Name", "false"], ["Last viewed", "false"], ["Last edited", "false"]]]);
  } finally { await context.close(); }
});

test("a project's top page leads with Recent, one row of the cards' grid, then All files; a resize changes how many stand across, and a search replaces it", async () => {
  const { context, page } = await home("place=gearbox&recents=many");
  try {
    // Two labels, the body's size at medium weight in the foreground, each 8px over what it labels: Recent 16px under the
    // head, All files 16px under Recent's row.
    const labels = page.locator("[data-library-content] h2");
    assert.deepEqual(await labels.allTextContents(), ["Recent", "All files"]);
    assert.deepEqual([await type(labels.nth(0)), await type(labels.nth(1)), (await style(labels.nth(0), "color"))[0]], ["13px 20px 500", "13px 20px 500", await token(page, "--foreground")]);
    const head = await box(page.locator("[data-library-head]"));
    const [recentLabel, allLabel] = [await box(labels.nth(0)), await box(labels.nth(1))];
    const row = await box(page.getByRole("list", { name: "Recent" }));
    const folders = await box(page.locator("[data-library-folders]"));
    assert.deepEqual([recentLabel.x, recentLabel.y - head.bottom, row.y - recentLabel.bottom, allLabel.y - row.bottom, folders.y - allLabel.bottom], [232 + 16, 16, 8, 16, 8]);
    // One row of the cards' grid: as many as fit across at 1440px beside the sidebar, five, in the listing's columns (its
    // other files' tiles fill five).
    const cards = () => page.locator("[data-library-recent] .cad-library-card").evaluateAll((nodes) => nodes.map((node) => { const { x, y, width } = node.getBoundingClientRect(); return [x, y, width]; }));
    const listed = await page.locator("[data-library-all] [data-library-other-files] > li").evaluateAll((nodes) => nodes.slice(0, 5).map((node) => { const { x, width } = node.getBoundingClientRect(); return [x, width]; }));
    const shown = await cards();
    assert.deepEqual([shown.length, new Set(shown.map(([, y]) => y)).size, shown.map(([x, , width]) => [x, width])], [5, 1, listed]);
    // Newest first; each card's line its activity alone, as a card's always is.
    assert.deepEqual(await page.locator("[data-library-recent] [data-library-label]").allTextContents(), ["plate_0.dxf", "plate_1.dxf", "plate_2.dxf", "housing.xbf", "plate_3.dxf"]);
    assert.equal(await page.locator("[data-library-recent] [data-library-status]").first().textContent(), "Viewed 30m ago");
    // A narrower window takes cards out of the row, a wider one puts them back, with no reload.
    await page.setViewportSize({ width: 1100, height: 900 });
    await page.waitForFunction(() => document.querySelectorAll("[data-library-recent] .cad-library-card").length === 3);
    assert.equal(new Set((await cards()).map(([, y]) => y)).size, 1);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForFunction(() => document.querySelectorAll("[data-library-recent] .cad-library-card").length === 5);
    // A search replaces it, labels and all, with the search's results.
    await page.getByRole("searchbox", { name: "Search models" }).fill("plate_1");
    await page.locator("[data-library-recent]").waitFor({ state: "detached" });
    await page.getByRole("link", { name: "Open plate_1.dxf", exact: true }).waitFor();
    assert.equal(await labels.count(), 0);
    // The list: at most five rows, under a header of their own with the listing's columns, no Where.
    await page.getByRole("searchbox", { name: "Search models" }).fill("");
    await page.getByRole("button", { name: "List" }).click();
    const rows = page.getByRole("list", { name: "Recent" }).locator(".cad-library-row");
    await rows.first().waitFor();
    assert.equal(await rows.count(), 5);
    assert.deepEqual(await page.locator("[data-library-recent] [data-library-columns] span").allTextContents(), ["Name", "Type", "Last viewed", "Last edited"]);
    assert.equal(await page.locator("[data-column=where], [data-column=size], [data-column=created]").count(), 0);
  } finally { await context.close(); }
  // Below the top, the folder's page as it is: no Recent and no labels.
  const below = await home("place=gearbox&path=housing&recents=many", undefined, { waitFor: "[data-library-folders]" });
  try {
    assert.deepEqual([await below.page.locator("[data-library-recent]").count(), await below.page.locator("[data-library-content] h2").count()], [0, 0]);
  } finally { await below.context.close(); }
});

test("at a phone's scale the home's rows, texts and gutters are the phone's: 46px folders, 52px list rows, each text 2px up, the same 16px inset", async () => {
  const { context, page } = await home("place=gearbox", { width: 390, height: 844 });
  try {
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    await still(page);
    assert.deepEqual(await px(page.locator("[data-library-content]"), "paddingTop", "paddingLeft", "paddingRight"), ["16px", "16px", "16px"]);
    const card = page.locator("[data-library-all] .cad-library-card").first();
    assert.deepEqual([(await box(page.locator("[data-library-folders] > li").first())).height, await type(page.locator("[data-library-title]")), await type(card.locator("[data-library-label]")),
      await type(card.locator("[data-library-status]")), (await box(card.locator("[data-library-format]"))).height], [46, "17px 22px 500", "15px 20px 500", "15px 20px 400", 28]);
    await page.getByRole("button", { name: "List" }).click();
    const row = page.locator("[data-library-all] .cad-library-row").filter({ has: page.locator("[data-library-picture]") }).first();
    await row.waitFor();
    // Its two actions, a finger's 36px each, stand clear of its last column.
    const [open, action, updated] = [await box(row), await box(row.getByRole("button").last()), await box(row.locator('[data-column="edited"]'))];
    assert.deepEqual([open.height, (await box(page.locator("[data-library-all] [data-library-columns]"))).height, action.height, updated.right <= (await box(row.getByRole("button").nth(1))).x], [52, 36, 36, true]);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "nothing wider than the phone");
  } finally { await context.close(); }
});

test("a file that is no document is a 46px tile of the folders' family after the cards: pressed as a button it opens in an app, and its ⋯ at its right end holds Open in", async () => {
  const { context, page } = await home("place=gearbox");
  try {
    // After the cards, a grid of its own 16px under them, in the cards' columns: a folder tile's box (its 1px border and
    // 10px corners round a 12px inset round one 20px line, 46px), its kind's glyph where a folder's is, its name a
    // card's name; a button, not a link.
    const tiles = page.getByRole("list", { name: "Other files" });
    const cards = await box(page.locator("[data-library-all]").getByRole("list", { name: "Files", exact: true }));
    const [first, second] = [tiles.locator("> li").nth(0), tiles.locator("> li").nth(1)];
    assert.equal(Math.round((await box(tiles)).y - cards.bottom), 16);
    const columns = await page.locator("[data-library-all] .cad-library-card").evaluateAll((nodes) => nodes.map((node) => { const { x, width } = node.getBoundingClientRect(); return [x, width]; }));
    const across = await tiles.locator("> li").evaluateAll((nodes) => nodes.map((node) => { const { x, width, height } = node.getBoundingClientRect(); return [x, width, height]; }));
    assert.deepEqual([across.every(([, , height]) => height === 46), across.slice(0, columns.length).map(([x, width]) => [x, width])], [true, columns]);
    const folder = page.locator("[data-library-folders] > li").first();
    assert.deepEqual(await px(first, "borderTopWidth", "borderTopLeftRadius", "backgroundColor"), await px(folder, "borderTopWidth", "borderTopLeftRadius", "backgroundColor"));
    const [tile, glyph, label] = [await box(first), await box(first.locator("svg").first()), first.locator("[data-library-label]")];
    assert.deepEqual([glyph.x - tile.x, glyph.width, Math.round(glyph.y + glyph.height / 2 - tile.y)], [(await box(folder.locator("svg"))).x - (await box(folder)).x, 16, 23]);
    assert.deepEqual([await label.textContent(), await type(label), (await style(label, "color"))[0]], ["bearing-6204-datasheet.pdf", "13px 20px 500", await token(page, "--foreground")]);
    const press = page.getByRole("button", { name: "Open build.py", exact: true });
    assert.deepEqual([await press.getAttribute("href"), await second.locator("a").count(), await second.locator("[data-library-picture], [data-library-format], [data-library-status]").count(), (await style(press, "cursor"))[0]],
      [null, 0, 0, "pointer"]);
    // Its ⋯, there under the pointer, as a card's: in a square at its right end as tall as its inside, so the button is
    // padded alike on every side (10px) and its glyph ends 16px in; a long name ends where that square starts.
    const more = first.getByRole("button", { name: "Actions for bearing-6204-datasheet.pdf" });
    assert.equal((await style(more, "opacity"))[0], "0");
    await first.hover();
    await page.waitForFunction((node) => getComputedStyle(node).opacity === "1", await more.elementHandle());
    const [button, dots] = [await box(more), await box(more.locator("svg"))];
    assert.deepEqual([button.y - tile.y - 1, tile.bottom - 1 - button.bottom, tile.right - 1 - button.right, button.width, tile.right - 1 - dots.right], [10, 10, 10, 24, 16]);
    assert.ok(await label.evaluate((node) => node.scrollWidth > node.clientWidth), "the long name truncates");
    assert.equal(Math.round((await box(label)).right), Math.round(tile.right - 1 - 44));
    // The keyboard reaches it as it reaches a card, with the same ring, and its ⋯ shows in focus; Enter opens it: here, a
    // script, in the first app the host lists.
    await page.mouse.move(700, 20);
    await press.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    const brand = await token(page, "--brand");
    assert.ok((await style(second, "boxShadow"))[0].includes(`${brand} 0px 0px 0px 1px`), "the focused tile's ring");
    await page.waitForFunction((node) => getComputedStyle(node).opacity === "1", await second.getByRole("button", { name: "Actions for build.py" }).elementHandle());
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => window.homeOpenedIn?.length === 1);
    // A file the OS's handler takes opens with it; the page goes nowhere and no menu opens.
    await page.getByRole("button", { name: "Open bearing-6204-datasheet.pdf", exact: true }).click();
    await page.waitForFunction(() => window.homeOpenedIn?.length === 2);
    assert.deepEqual([await page.evaluate(() => window.homeOpenedIn.map(({ path, target, app }) => [path.split("/").pop(), target, app])), page.url(), await page.getByRole("menu").count()],
      [[["build.py", "source", "vscode"], ["bearing-6204-datasheet.pdf", "source", "default"]], `${origin}/?place=gearbox`, 0]);
    // Its ⋯: Open in (the host's apps), Copy path and the file manager.
    await second.hover();
    await second.getByRole("button", { name: "Actions for build.py" }).click();
    await page.getByRole("menuitem", { name: "Open in", exact: true }).click();
    assert.deepEqual([await page.getByRole("menu", { name: "Open in" }).getByRole("menuitem").allTextContents(), await page.getByRole("menu").first().locator(":scope [role=menuitem]").allTextContents()],
      [["VS Code", "PyCharm"], ["Open in", "Copy path", "Show in file manager"]]);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    // In the list, a row after the documents' rows, its extension its Type.
    await page.getByRole("button", { name: "List" }).click();
    const rows = page.locator("[data-library-all] .cad-library-row");
    await rows.first().waitFor();
    const named = await rows.evaluateAll((nodes) => nodes.map((node) => [node.querySelector("[data-library-label]").textContent, node.querySelector('[data-column="type"]').textContent]));
    assert.deepEqual(named.slice(3), [["gearbox.xbf", "Assembly"], ["spur_gear.xbf", "Part"], ["bearing-6204-datasheet.pdf", "PDF"], ["build.py", "PY"], ["NOTES.md", "MD"],
      ["gearbox.f3d", "F3D"], ["tolerances.dat", "DAT"], ["Makefile", "—"]]);
  } finally { await context.close(); }
  // Nothing here opens it: said in the place's line, under the heading row.
  const none = await home("place=gearbox&path=housing/v3");
  try {
    await none.page.getByRole("button", { name: "Open run.sh", exact: true }).click();
    const said = none.page.getByRole("alert");
    assert.deepEqual([await said.textContent(), (await style(said, "color"))[0], await type(said)], ["No app on this computer opens run.sh.", await token(none.page, "--destructive"), "13px 20px 400"]);
  } finally { await none.context.close(); }
  // A finger's phone: the same 46px tile, one across, its ⋯ a finger's 36px, always there, still padded alike (4px) with
  // its glyph 16px in.
  const phone = await home("place=gearbox", { width: 390, height: 844 }, { hasTouch: true });
  try {
    const { page } = phone;
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    await still(page);
    const first = page.getByRole("list", { name: "Other files" }).locator("> li").first();
    const more = first.getByRole("button", { name: "Actions for bearing-6204-datasheet.pdf" });
    const [tile, button, dots] = [await box(first), await box(more), await box(more.locator("svg"))];
    assert.deepEqual([tile.x, tile.width, tile.height, (await style(more, "opacity"))[0], button.width, button.y - tile.y - 1, tile.right - 1 - button.right, tile.right - 1 - dots.right],
      [16, 358, 46, "1", 36, 4, 4, 16]);
  } finally { await phone.context.close(); }
});

test("a search's result that cad does not open is a 46px tile after the cards, and the list's rows after the documents' have no blank cell", async () => {
  const { context, page } = await home("place=gearbox");
  try {
    await page.getByRole("searchbox", { name: "Search models" }).fill("gearbox");
    const tiles = page.getByRole("list", { name: "Other files" });
    await tiles.getByRole("button", { name: "Open gearbox.f3d", exact: true }).waitFor();
    await page.getByRole("link", { name: "Open gearbox.xbf", exact: true }).waitFor();
    // Measured as drawn: the card above, the file a 46px tile of the folders' size 16px under the cards, in their column.
    const cards = await box(page.getByRole("list", { name: "Files", exact: true }));
    const [card, tile] = [await box(page.locator(".cad-library-card").first()), await box(tiles.locator("> li").first())];
    assert.deepEqual([tile.height, Math.round((await box(tiles)).y - cards.bottom), tile.x, tile.width, tile.y > card.bottom],
      [46, 16, card.x, card.width, true]);
    assert.equal(await page.locator(".cad-library-card", { hasText: "gearbox.f3d" }).count(), 0, "no card for it");
    // The list: its rows after the documents', every cell drawn with something in it.
    await page.getByRole("button", { name: "List" }).click();
    const rows = page.locator(".cad-library-row");
    // Await the condition, not the first row that is there: the search's results stay on screen across the switch, never the whole folder.
    await page.waitForFunction(() => JSON.stringify([...document.querySelectorAll(".cad-library-row [data-library-label]")].map((node) => node.textContent)) === '["gearbox.xbf","gearbox.f3d"]');
    const drawn = await rows.evaluateAll((nodes) => nodes.map((node) => [node.querySelector("[data-library-label]")?.textContent,
      [...node.querySelectorAll("[data-column]")].map((cell) => cell.textContent.trim())]));
    assert.deepEqual(drawn.map(([name]) => name), ["gearbox.xbf", "gearbox.f3d"]);
    assert.equal(drawn.every(([, cells]) => cells.length === 3 && cells.every(Boolean)), true, JSON.stringify(drawn));
    assert.equal(await page.getByText("Standalone").count(), 0);
  } finally { await context.close(); }
});

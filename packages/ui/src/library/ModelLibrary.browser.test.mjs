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
  const context = await browser.newContext({ viewport, ...options });
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
    // The sidebar is the viewer's panel (its surface), its places a navigation in it.
    const surface = page.locator("aside[data-library-sidebar]");
    const sidebar = page.getByRole("navigation", { name: "Places" });
    const side = await box(surface);
    assert.deepEqual([side.x, side.width, side.y, side.bottom], [0, 232, navbar.bottom, 900], "232px at the window's edge, from the navbar to the bottom");
    assert.deepEqual(await style(surface, "backgroundColor", "borderRightWidth"), [await token(page, "--sidebar"), "1px"]);
    assert.equal(await sidebar.evaluate((node) => Boolean(node.closest("aside[data-library-sidebar]"))), true);
    // The logo first, its drawn mark on the panel's 16px inset (its 16px image 14px in, the artwork 2px inside it); then
    // its toggle, the next 28px tile edge to edge with it; then Home.
    const toggle = page.locator('[data-viewer-navbar] [data-navbar-panel="left"]');
    assert.equal((await box(page.locator("[data-viewer-navbar] [data-navbar-logo] img"))).x + 2, 16);
    assert.deepEqual([await toggle.getAttribute("aria-expanded"), (await box(toggle)).x, (await box(toggle.locator("svg"))).x, (await box(toggle)).height], ["true", 36, 42, 28]);
    const lead = await page.locator("[data-viewer-navbar]").evaluate((bar) => [...bar.querySelectorAll('[data-navbar-panel="left"], [data-navbar-logo], h1')]
      .map((node) => node.getAttribute("data-navbar-panel") ?? node.getAttribute("data-navbar-logo") ?? node.textContent));
    assert.deepEqual(lead, ["home", "left", "Home"]);
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
    // The place: its name the page's one larger text, 24px in from the sidebar and 20px under the navbar; Sort and the
    // layout at the row's right end, every control the scale's 28px.
    const title = page.locator(".cad-library-title");
    assert.deepEqual([await title.textContent(), ...(await style(title, "fontSize", "lineHeight", "fontWeight"))], ["Recents", "15px", "20px", "600"]);
    const toolbar = await box(page.locator(".cad-library-toolbar"));
    assert.deepEqual([toolbar.x, toolbar.y, toolbar.right], [232 + 24, navbar.bottom + 20, 1440 - 24]);
    for (const name of ["Sort by Last activity", "Grid", "List"]) assert.equal((await box(page.getByRole("button", { name }))).height, 28, name);
    assert.equal(Math.round((await box(page.getByRole("button", { name: "List" }))).right), 1440 - 24);
    // Grid and list are one segmented control: a 28px track on the muted fill, each option's face 2px in, the chosen one
    // raised on the page's colour.
    const layout = page.getByRole("group", { name: "Layout" });
    const faces = await page.locator("[data-segment] > span").evaluateAll((nodes) => nodes.map((node) => {
      const { width, height } = node.getBoundingClientRect(); return [Math.round(width), Math.round(height), getComputedStyle(node).backgroundColor]; }));
    assert.deepEqual([(await box(layout)).height, (await box(layout)).width, ...(await style(layout, "backgroundColor"))], [28, 64, await token(page, "--muted")]);
    assert.deepEqual(faces, [[28, 24, await token(page, "--background")], [28, 24, "rgba(0, 0, 0, 0)"]]);
    // The kinds' chips, a row of their own 12px under the heading row and 16px over the cards: the panel's tab pills,
    // their words on the place's line, All on.
    const kinds = page.getByRole("group", { name: "Show" });
    const chips = await kinds.getByRole("button").evaluateAll((nodes) => nodes.map((node) => [node.getAttribute("aria-label"), node.getAttribute("aria-pressed"),
      Math.round(node.getBoundingClientRect().height), getComputedStyle(node).paddingLeft]));
    assert.deepEqual(chips, [["All, 8", "true", 28, "6px"], ["3D models, 6", "false", 28, "6px"], ["Drawings, 1", "false", 28, "6px"], ["Robots, 1", "false", 28, "6px"]]);
    const row = await box(kinds);
    assert.deepEqual([row.x, row.y], [232 + 24 - 6, toolbar.bottom + 12]);
    assert.deepEqual(await style(kinds.getByRole("button", { name: "All, 8" }), "backgroundColor", "fontWeight"), [await token(page, "--accent"), "400"]);
    assert.equal((await box(page.locator(".cad-library-card").first())).y, row.bottom + 16);
    await kinds.getByRole("button", { name: "Drawings, 1" }).click();
    assert.deepEqual(await page.locator(".cad-library-card .cad-library-open").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("aria-label"))), ["Open layered.dxf"]);
    await kinds.getByRole("button", { name: "All, 8" }).click();
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

test("a home too narrow for its sidebar collapses it and keeps its heading; at a phone's width every control is a finger's", async () => {
  // A pane 700px wide in a wider window: the home measures itself, never the window.
  const pane = await home("width=700", { width: 1300, height: 800 });
  try {
    const { page } = pane;
    // Collapsed by its width, nothing of it left: the place from the pane's edge, on the narrow gutters.
    assert.equal(await page.getByRole("navigation", { name: "Places" }).count(), 0);
    assert.equal(await page.locator('[data-viewer-navbar] [data-navbar-panel="left"]').getAttribute("aria-expanded"), "false");
    assert.deepEqual([(await box(page.locator(".cad-library-content"))).x, (await box(page.locator(".cad-library-title"))).x], [0, 16]);
    // No menu of places on the heading: Home in the navbar, the place's name in its own row.
    assert.deepEqual([await page.locator("[data-navbar-home-left] h1").textContent(), await page.locator(".cad-library-title").textContent(),
      await page.getByRole("button", { name: /^Places/ }).count()], ["Home", "Recents", 0]);
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
    assert.deepEqual(await style(page.locator("[data-navbar-home-left] h1"), "fontSize"), ["15px"]);
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
    const content = page.locator(".cad-library-content");
    assert.deepEqual([(await box(content)).x, (await box(page.locator(".cad-library-title"))).x], [232, 256]);
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
    await page.waitForFunction(() => document.querySelector(".cad-library-content").getBoundingClientRect().width === 1600);
    assert.deepEqual([(await box(content)).x, await page.locator(SIDEBAR).isVisible(), await kept(page)], [0, false, { open: false }]);
    // Its key (Ctrl+\ off a Mac) opens it again, their choice too, and it then holds in a narrow window.
    await page.keyboard.press("Control+Backslash");
    await page.locator(SIDEBAR).waitFor({ state: "visible" });
    await page.setViewportSize({ width: 700, height: 900 });
    await page.waitForFunction(() => document.querySelector(".cad-library-content").getBoundingClientRect().width === 700 - 232);
    assert.deepEqual([(await box(content)).x, await kept(page)], [232, { open: true }]);
  } finally { await context.close(); }
});

test("resting on the toggle peeks the collapsed sidebar as a card over the place, 4px in, pushing nothing; it goes when left, and the toggle pins it", async () => {
  const { context, page } = await home('panel={"open":false}');
  try {
    const navbar = await box(page.locator("[data-viewer-navbar]"));
    const content = page.locator(".cad-library-content");
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
    await page.locator('.cad-library-title:text-is("Pinned")').waitFor();
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
    await page.waitForFunction(() => document.querySelector(".cad-library-content").getBoundingClientRect().x === 232);
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
    assert.deepEqual([(await box(page.locator(SIDEBAR))).width, (await box(page.locator(".cad-library-content"))).x, await kept(page)], [332, 332, null]);
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
    assert.deepEqual([(await box(again.page.locator(SIDEBAR))).width, (await box(again.page.locator(".cad-library-content"))).x], [300, 300]);
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
    assert.equal(await cog.evaluate((node) => node === document.activeElement), true);
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
    assert.equal(await page.locator(".cad-library-title").textContent(), "gearbox");
    await page.locator(TOGGLE).tap();
    await sheet.waitFor();
    await page.locator(TOGGLE).tap();
    await sheet.waitFor({ state: "detached" });
    // A tap beside the sheet closes it too, and leaves the page as it was.
    await page.locator(TOGGLE).tap();
    await sheet.waitFor();
    await page.touchscreen.tap(360, 600);
    await sheet.waitFor({ state: "detached" });
    assert.equal(await page.locator(".cad-library-title").textContent(), "gearbox");
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
    assert.equal(await page.locator(".cad-library-title").textContent(), "gearbox");
    // A plain click: Recents here, with no navigation of the page, and no menu.
    await logo.click();
    await page.locator('.cad-library-title:text-is("Recents")').waitFor();
    assert.deepEqual([page.url(), await page.getByRole("menu").count(), context.pages().length], [`${origin}/?place=gearbox`, 0, 1]);
  } finally { await context.close(); }
  // A host with no addresses (an app's frame): the same logo, a button.
  const framed = await home("place=gearbox&links=0");
  try {
    assert.equal(await framed.page.getByRole("link", { name: "Home" }).count(), 0);
    await framed.page.getByRole("button", { name: "Home" }).click();
    await framed.page.locator('.cad-library-title:text-is("Recents")').waitFor();
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

test("the kinds' chips wrap on a narrow page, and at a phone's scale every chip and the layout's options are a finger's", async () => {
  const narrow = await home("width=240", { width: 800, height: 800 });
  try {
    const { page } = narrow;
    const content = await box(page.locator(".cad-library-content"));
    const chips = await page.getByRole("group", { name: "Show" }).getByRole("button").evaluateAll((nodes) => nodes.map((node) => {
      const { y, right } = node.getBoundingClientRect(); return [Math.round(y), Math.round(right)]; }));
    assert.ok(new Set(chips.map(([y]) => y)).size > 1, `the chips wrap: ${JSON.stringify(chips)}`);
    assert.ok(chips.every(([, right]) => right <= content.right - 16), "no chip past the place's edge");
  } finally { await narrow.context.close(); }
  const phone = await home("", { width: 390, height: 844 });
  try {
    const { page } = phone;
    await page.locator('[data-viewer-layout="mobile"]').waitFor();
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    for (const name of ["All, 8", "Robots, 1", "Grid", "List"]) assert.equal((await box(page.getByRole("button", { name }))).height, 36, name);
    assert.deepEqual(await page.locator("[data-segment] > span").evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().height))), [32, 32]);
    assert.deepEqual(await style(page.getByRole("button", { name: "All, 8" }), "fontSize"), ["15px"]);
  } finally { await phone.context.close(); }
});

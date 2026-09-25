import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Page,
} from "@playwright/test";

/**
 * The sidebar as sections (Claude Code's shape): the `New` row, a grey header
 * per project with a flat list of threads under it, `Pinned` above them all,
 * and the filter menu behind the sliders glyph.
 *
 * Everything here is a fact the panel is *for* — which threads it shows, in
 * what order, under which header, and what each row's glyph says — so it is
 * driven through the real controls rather than through the stores. Two
 * projects, because half of these rules only mean something with more than
 * one: a `+` that started a thread in the wrong project, or a filter that was
 * per project when it should be global, both look right with one.
 *
 * The agent is `tests/fake-agent/index.mjs` (`HARDCORE_FAKE_AGENT`): a
 * session needs one to exist, and the glyph test needs a turn that runs and
 * a turn that stops to ask.
 */
declare const window: {
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: { set(patch: Record<string, unknown>): Promise<unknown> };
    sessions: {
      create(request: {
        projectId: string;
        agentId: string;
        gitMode: string;
      }): Promise<{ id: string }>;
      rename(request: { id: string; title: string }): Promise<unknown>;
      archive(request: { id: string; archived: boolean }): Promise<unknown>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

let app: ElectronApplication;
let page: Page;
let base: string;
let alpha: { id: string; name: string };
let beta: { id: string; name: string };

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-sidebar-e2e-")));
  const alphaDir = path.join(base, "alpha-project");
  const betaDir = path.join(base, "beta-project");
  for (const dir of [alphaDir, betaDir]) {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "README.md"), "# A project\n");
  }

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${path.join(base, "user-data")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  page.on("pageerror", (error) => console.error(`[renderer] ${error.message}`));
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(
    (root) => window.hardcore.settings.set({ worktreeRoot: root }),
    path.join(base, "worktrees"),
  );

  alpha = await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), alphaDir);
  beta = await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), betaDir);
  await expect(sidebar().getByRole("button", { name: `Collapse ${alpha.name}` })).toBeVisible();

  // Dark, for comparability with the other suites' screenshots — and written
  // *after* the panel is up. A theme set while the renderer's own first read
  // of the settings is still in flight is a theme that read overwrites, and
  // the shots come back in light with nothing else wrong.
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(base, { recursive: true, force: true });
});

/**
 * `New` replaced `New chat`: a plus in a ring and one word, and it is the
 * whole nav list — adding a folder is `Open folder…` on the project chip's
 * menu, not a row here. Search and the filters are in the panel's header
 * beside the app's name, Settings in the footer.
 */
test("the nav list is `New`, and `New chat` is gone", async () => {
  await expect(sidebar().getByRole("button", { name: "New", exact: true })).toBeVisible();
  await expect(sidebar().getByRole("button", { name: "New chat", exact: true })).toHaveCount(0);
  await expect(sidebar().getByRole("button", { name: "Add project" })).toHaveCount(0);
  await expect(sidebar().getByRole("button", { name: "Search", exact: true })).toBeVisible();
  await expect(sidebar().getByRole("button", { name: "Filters" })).toBeVisible();
  await expect(sidebar().getByRole("button", { name: "Settings" })).toBeVisible();

  // Each project is a header, not a row with a folder icon and children.
  await expect(sidebar().getByRole("button", { name: `Collapse ${beta.name}` })).toBeVisible();
});

/**
 * A project's header is its name, its collapse and `+`. The search glyph and
 * the sliders that used to appear on it on hover are the panel's now: one
 * search box for every thread, one filter menu for a set of settings that
 * was always global. Hovered, because that is the state the two of them
 * used to appear in — a header that grows a control under the pointer is
 * exactly what this checks is gone.
 */
test("a project's header has + and nothing else", async () => {
  const header = sectionOf(alpha.id).locator("[data-sidebar-section-header]");
  await header.hover();
  await expect(header.getByRole("button", { name: `New chat in ${alpha.name}` })).toBeVisible();
  await expect(header.getByRole("button", { name: `Search ${alpha.name}` })).toHaveCount(0);
  await expect(header.getByRole("button", { name: "Filters" })).toHaveCount(0);
  // One filter menu in the panel, not one per project.
  await expect(sidebar().getByRole("button", { name: "Filters" })).toHaveCount(1);
  await shoot("sidebar-header.png");
});

/**
 * The collapse is the header, and it is a *preference*: `settings.sidebar`
 * in sqlite rather than a set in a store, so the section a person shut is
 * still shut after a relaunch. Reloading the renderer is the cheap version of
 * that: the stores are rebuilt from main either way.
 */
test("a project's section collapses and expands, and survives a reload", async () => {
  const session = await createSession(alpha.id, "Aspen");
  const row = page.locator(`[data-session-row="${session}"]`);
  await expect(row).toBeVisible();

  await sidebar().getByRole("button", { name: `Collapse ${alpha.name}` }).click();
  await expect(row).toHaveCount(0);
  await expect(sidebar().getByRole("button", { name: `Expand ${alpha.name}` })).toBeVisible();

  await page.reload();
  await expect(sidebar().getByRole("button", { name: `Expand ${alpha.name}` })).toBeVisible();
  await expect(page.locator(`[data-session-row="${session}"]`)).toHaveCount(0);

  await sidebar().getByRole("button", { name: `Expand ${alpha.name}` }).click();
  await expect(page.locator(`[data-session-row="${session}"]`)).toBeVisible();
});

/**
 * `+` on a header binds *that* project. The one it is not on is the point:
 * a `+` wired to the active project would pass with one project and start
 * every thread in the wrong folder with two.
 */
test("a header's + opens that project's new-session screen", async () => {
  await sidebar().getByRole("button", { name: `New chat in ${beta.name}` }).click();
  await expect(page.getByRole("heading", { name: `What should we build in ${beta.name}?` })).toBeVisible();

  await sidebar().getByRole("button", { name: `New chat in ${alpha.name}` }).click();
  await expect(page.getByRole("heading", { name: `What should we build in ${alpha.name}?` })).toBeVisible();
});

/**
 * A pinned thread lives in `Pinned` and nowhere else — the behaviour the
 * design is copied from, and the only one that makes a pin mean anything: a
 * row that stayed under its project too would be a duplicate of itself.
 */
test("pinning lifts a row into Pinned, and unpinning puts it back", async () => {
  const row = page.locator("[data-session-row]").filter({ hasText: "Aspen" });
  await row.hover();
  await row.getByRole("button", { name: /actions$/ }).click();
  await page.getByRole("menuitem", { name: "Pin", exact: true }).click();

  await expect(sidebar().getByText("Pinned", { exact: true })).toBeVisible();
  await expect(page.locator("[data-session-row][data-pinned]")).toHaveCount(1);
  // Once, not twice, and the section it left is empty.
  await expect(page.locator("[data-session-row]").filter({ hasText: "Aspen" })).toHaveCount(1);
  await expect(sectionOf(alpha.id).locator("[data-session-row]")).toHaveCount(0);
  // The row names the project it came from, since its header no longer does.
  await expect(row.locator("[data-session-project]")).toContainText(alpha.name);
  await shoot("sidebar-pinned.png");

  await row.hover();
  await row.getByRole("button", { name: /actions$/ }).click();
  await page.getByRole("menuitem", { name: "Unpin" }).click();
  await expect(sidebar().getByText("Pinned", { exact: true })).toHaveCount(0);
  await expect(page.locator("[data-session-row][data-pinned]")).toHaveCount(0);
});

/**
 * The filter menu: what the list holds, and in what order. The settings are
 * global even though the menu is opened from one project's header, which is
 * why the assertions below are about the whole list.
 */
test("the filter menu reorders the list and shows the archived threads", async () => {
  const archived = await createSession(alpha.id, "Cedar");
  await createSession(alpha.id, "Birch");
  await page.evaluate((id) => window.hardcore.sessions.archive({ id, archived: true }), archived);

  // Active is the default, so the archived one is not here and the rest are
  // newest first.
  await expect.poll(titles).toEqual(["Birch", "Aspen"]);

  await openFilters();
  await shoot("sidebar-filters.png");
  await choose("Sort by", "Name");
  await expect.poll(titles).toEqual(["Aspen", "Birch"]);

  await openFilters();
  await choose("Status", "Archived");
  await expect.poll(titles).toEqual(["Cedar"]);

  await openFilters();
  await choose("Status", "All");
  await expect.poll(titles).toEqual(["Aspen", "Birch", "Cedar"]);

  // And back, so the glyph test below reads a list it recognises.
  await openFilters();
  await choose("Status", "Active");
  await openFilters();
  await choose("Sort by", "Last activity");
  await expect.poll(titles).toEqual(["Birch", "Aspen"]);
});

/**
 * The project chip's menu, which is where a folder is chosen *and* where a
 * new one is added (Codex's shape): `Recent`, the projects in order of when
 * they were last worked in, a check on the one this screen is for, then
 * `Open folder…`.
 *
 * Two projects is the whole point. `alpha` has threads and `beta` has none,
 * so `alpha` is first — while the check is on `beta`, whose new-session
 * screen this is. A menu that sorted by "the active one first", or a check
 * drawn on the first row, would pass with one project and lie with two.
 *
 * This is the suite with two projects, which is why the composer's chip is
 * tested here rather than in `session.spec.ts`.
 */
test("the project chip lists the recent folders, and ends in `Open folder…`", async () => {
  await sidebar().getByRole("button", { name: `New chat in ${beta.name}` }).click();
  await expect(page.getByRole("heading", { name: `What should we build in ${beta.name}?` })).toBeVisible();

  await page.locator("[data-chip=project]").click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByText("Recent", { exact: true })).toBeVisible();
  // In order, and `Open folder…` last. `alpha` has the sessions, so it leads.
  await expect(menu.getByRole("menuitem")).toHaveText([alpha.name, beta.name, "Open folder…"]);
  // No `No folder` row: a session always belongs to one.
  await expect(menu.getByRole("menuitem", { name: "No folder" })).toHaveCount(0);
  await shoot("project-menu.png");

  // The check is on the active project, not on the first row.
  const checked = (name: string) =>
    menu.getByRole("menuitem", { name }).locator("svg").count();
  expect(await checked(beta.name)).toBe(1);
  expect(await checked(alpha.name)).toBe(0);

  // And picking one switches to it.
  await menu.getByRole("menuitem", { name: alpha.name }).click();
  await expect(page.getByRole("heading", { name: `What should we build in ${alpha.name}?` })).toBeVisible();
});

/**
 * The leading glyph is the session's state, which is the thing a sidebar is
 * read for: a pulse while a turn streams, and an amber triangle when the
 * agent has stopped to ask. Both come from the index's status, so this is
 * also the proof that main's `session.status` reaches the row.
 */
test("the state glyph follows a turn that runs and then asks", async () => {
  const row = page.locator("[data-session-row]").filter({ hasText: "Birch" });
  await row.getByRole("button", { name: "Birch", exact: true }).click();
  await expect(page.locator("[data-session-view]")).toBeVisible();
  await expect(row.locator("[data-session-glyph=idle]")).toBeVisible();

  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("slow");
  await composer.press("Enter");
  await expect(row.locator("[data-session-glyph=running]")).toBeVisible();
  await expect(row).toHaveAttribute("data-status", "running");
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(row.locator("[data-session-glyph=idle]")).toBeVisible({ timeout: 20_000 });

  await composer.fill("permission");
  await composer.press("Enter");
  await expect(row.locator("[data-session-glyph=waiting]")).toBeVisible();
  await expect(row).toHaveAttribute("data-status", "waiting");
  await shoot("sidebar-waiting.png");

  await page
    .locator("[data-permission][data-outcome=pending]")
    .getByRole("button", { name: "Yes", exact: true })
    .click();
  await expect(row.locator("[data-session-glyph=idle]")).toBeVisible({ timeout: 20_000 });
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function sidebar() {
  return page.getByTestId("sidebar");
}

function sectionOf(id: string) {
  return sidebar().locator(`[data-sidebar-section="${id}"]`);
}

/**
 * Every session title on screen, top to bottom. The row's title button is the
 * one without a label — the `…` beside it is `<title> actions`.
 */
function titles() {
  return page.locator("[data-session-row] > button:not([aria-label])").allInnerTexts();
}

async function createSession(projectId: string, title: string) {
  const id = await page.evaluate(
    async (project) => {
      const session = await window.hardcore.sessions.create({
        projectId: project,
        agentId: "claude-code",
        gitMode: "none",
      });
      return session.id;
    },
    projectId,
  );
  await page.evaluate((input) => window.hardcore.sessions.rename(input), { id, title });
  await expect(page.locator(`[data-session-row="${id}"]`)).toContainText(title);
  return id;
}

/**
 * Open the filter menu, which is in the panel's own header beside search —
 * one menu for the whole list, wherever the pointer happens to be. It used
 * to be a glyph on each project's header that only appeared on hover.
 */
async function openFilters() {
  await sidebar().getByRole("button", { name: "Filters" }).click();
  await expect(page.getByRole("menu").first()).toBeVisible();
}

/** Pick `value` under the `label` submenu of the open filter menu. */
async function choose(label: string, value: string) {
  await page.getByRole("menuitem", { name: new RegExp(`^${label}`) }).hover();
  await page.getByRole("menuitemradio", { name: value, exact: true }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

async function shoot(name: string) {
  await page.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}

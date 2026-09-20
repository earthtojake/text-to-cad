import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from "./cad-runtime";

/**
 * References, both ways (the CAD review's items 2 and 4).
 *
 *   - An agent names files in prose; the ones that exist are links that
 *     open in the explorer (`features/session/links`), the ones that do not
 *     are words.
 *   - A person types a reference into the composer and it becomes a chip
 *     (`features/session/composer`), sent as the plain token; the viewer's
 *     Add to prompt lands one in the box; the viewer's camera button
 *     attaches the viewport as an image.
 *
 * A temporary workspace contains the tiny STEP fixture and the paths the
 * fake agent names, without cataloging the developer’s checkout. The agent is
 * `tests/fake-agent`: "mention" makes it name files, and the composer's
 * text arrives at it unchanged, which is what `sessions.state` shows.
 */

declare const window: {
  innerWidth: number;
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: { set(patch: Record<string, unknown>): Promise<unknown> };
    runtime: { status(): Promise<{ state: string; cadgenVersion: string | null }> };
    sessions: {
      create(request: { projectId: string; agentId: string; gitMode: string; cwd: string }): Promise<{ id: string }>;
      prompt(request: { id: string; content: { type: "text"; text: string }[] }): Promise<{ stopReason: string }>;
      state(input: { id: string }): Promise<{ state: { turns: Array<{ role: string; parts: Array<Record<string, unknown>> }> }; live: boolean } | null>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const projectName = "workspace";
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");
const STEP = "tests/fixtures/cad/import-smoke.step";

let app: ElectronApplication;
let page: Page;
let userData: string;
let sessionId: string;

test.beforeAll(async () => {
  userData = cadTestProfile("references");
  const workspace = path.join(fs.realpathSync(userData), projectName);
  for (const file of ["README.md", "apps/desktop/AGENTS.md", STEP]) {
    const target = path.join(workspace, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    if (file === STEP) fs.copyFileSync(path.join(repoRoot, file), target);
    else fs.writeFileSync(target, `# ${path.basename(file)}\nReference fixture.\n`);
  }
  // The CAD runtime the app resolves on its own, as explorer.spec.ts does.
  const { CAD_DESKTOP_PYTHON: _unset, ...inherited } = process.env;
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...inherited, ...cadRegistryEnvironment(userData), NODE_ENV: "test", CADGEN_DAEMON: "0", CADGEN_CACHE_DIR: path.join(userData, "cad-cache"), CADGEN_DAEMON_STATE_DIR: path.join(userData, "cad-daemon"), HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  // Room for the session, the explorer and the viewer's sheet side by side.
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1440, 900));
  await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(1440);

  const project = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), workspace);
  await expect(page.getByText(projectName).first()).toBeVisible();

  const session = await page.evaluate(
    ({ projectId, cwd }) => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "none", cwd }),
    { projectId: project.id, cwd: workspace },
  );
  sessionId = session.id;
  await page.locator(`[data-session-row="${session.id}"]`).click();
  await expect(page.locator("[data-session-view]")).toBeVisible();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
});

test.afterAll(async () => {
  test.setTimeout(300_000);
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

/** The parts of the newest user turn. */
async function lastUserTurn() {
  const state = await page.evaluate((id) => window.hardcore.sessions.state({ id }), sessionId);
  const turns = state?.state.turns.filter((turn) => turn.role === "user") ?? [];
  return turns.at(-1)?.parts ?? [];
}

test("paths an agent writes are links when they exist, and open in the explorer", async () => {
  const outcome = await page.evaluate(
    ({ id, text }) => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text }] }),
    { id: sessionId, text: "mention some files" },
  );
  expect(outcome.stopReason).toBe("end_turn");

  // Real paths are buttons — prose, a code span, a CAD reference with its
  // selector — and a missing path or a version number is text.
  const readme = page.locator('[data-path-link="README.md"]');
  await expect(readme).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-path-link="apps/desktop/AGENTS.md"]')).toBeVisible();
  const part = page.locator(`[data-path-link="${STEP}"]`);
  await expect(part).toBeVisible();
  await expect(part).toHaveAttribute("data-path-selector", "o1");
  await expect(page.locator('[data-path-text="nope/missing.md"]')).toBeVisible();
  await expect(page.locator('[data-path-link="0.5.0"]')).toHaveCount(0);
  await expect(page.locator('[data-path-text="0.5.0"]')).toHaveCount(0);

  await readme.click();
  await expect(page.getByRole("tab", { name: /README\.md/ })).toBeVisible();
  await expect(page.locator("[data-transcript]")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: test.info().outputPath("transcript-links.png"), animations: "disabled" });
});

test("a typed reference is a chip, and is sent as its text", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.click();
  await page.keyboard.type(`make ${STEP}#o1.2 thicker, and #f3 `);
  const chips = page.locator("[data-composer] [data-reference-chip]");
  await expect(chips).toHaveCount(2);
  await expect(chips.nth(0)).toHaveAttribute("data-file", STEP);
  await expect(chips.nth(0)).toHaveAttribute("data-selector", "o1.2");
  await expect(chips.nth(0)).toContainText("import-smoke.step");
  await expect(chips.nth(0).locator("[data-selector-badge]")).toHaveText("o1.2");
  await expect(chips.nth(1)).toHaveAttribute("data-file", "");
  await expect(chips.nth(1)).toHaveAttribute("data-selector", "f3");
  await page.screenshot({ path: test.info().outputPath("composer-chips.png"), animations: "disabled" });

  // Backspace after the last chip takes the chip whole, not a character.
  await page.keyboard.press("Backspace");
  await page.keyboard.press("Backspace");
  await expect(chips).toHaveCount(1);
  await page.keyboard.type("#f3 please");

  // Sent as the words, chips as their tokens.
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-composer] [data-reference-chip]")).toHaveCount(0);
  await expect.poll(async () => (await lastUserTurn()).find((part) => part.type === "text")?.text).toBe(
    `make ${STEP}#o1.2 thicker, and #f3 please`,
  );
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 15_000 });
});

test("the viewer's Add to prompt lands a chip, and the camera an image", async () => {
  const status = await page.evaluate(() => window.hardcore.runtime.status());
  test.skip(!cadRuntimeReady(status), "no CAD runtime on this machine");
  test.setTimeout(240_000);

  // Open through the owned explorer even when running this test on its own.
  if (!(await page.getByRole("button", { name: "New tab", exact: true }).isVisible())) {
    await page.getByRole("button", { name: "Toggle explorer" }).click();
  }
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File" }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  const filter = page.getByLabel("Filter files");
  await filter.fill(STEP);
  await page.getByRole("option", { name: STEP, exact: false }).first().click();
  await expect(page.locator("canvas").first()).toBeVisible({ timeout: 60_000 });
  const tree = page.getByRole("list", { name: "Model", exact: true });
  await expect(tree).toBeVisible({ timeout: 90_000 });

  // Add to prompt from the tree's context menu names the file by its full path.
  const row = tree.getByRole("button", { name: /^Select / }).first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Add to prompt" }).click();
  const chip = page.locator("[data-composer] [data-reference-chip]");
  await expect(chip).toHaveCount(1);
  await expect(chip).toHaveAttribute("data-file", STEP);
  const selector = (await chip.getAttribute("data-selector")) ?? "";

  // The camera button: the viewport as a PNG attachment.
  await page.getByRole("button", { name: "Take snapshot", exact: true }).click();
  const captures = page.locator("[data-composer]").getByText(/import-smoke-.*\.png/);
  await expect(captures).toHaveCount(1, { timeout: 15_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: test.info().outputPath("composer-capture.png"), animations: "disabled" });

  // Sent: the text carries the token, the image goes as an image block.
  // A click in the middle of the box lands on the chip and selects it (a
  // click on a chip is a click on a chip); one at the right edge puts the
  // caret after it, where the words go.
  const box = (await page.getByPlaceholder("Do anything").boundingBox())!;
  await page.getByPlaceholder("Do anything").click({ position: { x: box.width - 8, y: box.height / 2 } });
  await page.keyboard.type("what is this");
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await lastUserTurn()).map((part) => part.type).sort()).toEqual(["image", "text"]);
  const parts = await lastUserTurn();
  expect(parts.find((part) => part.type === "text")?.text).toBe(`${selector ? `${STEP}#${selector}` : STEP} what is this`);
  expect((parts.find((part) => part.type === "image") as { mimeType: string }).mimeType).toBe("image/png");
});

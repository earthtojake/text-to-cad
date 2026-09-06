import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * The session UI against the fake agent (plan §12): new session → prompt →
 * streaming rows → permission answered → completed, then the other states
 * — cancelled, errored, resumed, signed out — each screenshotted into
 * `__screenshots__/session-*.png`. Look at them.
 *
 * `HARDCORE_FAKE_AGENT` makes main launch `tests/fake-agent` in place of
 * every adapter; the `showcase` prompt is the fake's Codex-shaped turn.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: { theme: string }): Promise<unknown> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let signedOutProject: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-session-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-scratch-"));
  fs.writeFileSync(path.join(project, "README.md"), "# Scratch\n\nA place to try things.\n");
  signedOutProject = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-signed-out-"));
  fs.writeFileSync(path.join(signedOutProject, ".fake-auth-required"), "");

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  // A renderer exception would otherwise show up as an empty page and a
  // timeout three assertions later.
  page.on("pageerror", (error) => {
    console.error(`[renderer] ${error.message}\n${error.stack ?? ""}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      console.error(`[renderer:${message.type()}] ${message.text()}`);
    }
  });
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate((value) => window.hardcore.settings.set({ theme: value }), "dark");
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
});

test.afterAll(async () => {
  await app?.close();
  for (const dir of [userData, project, signedOutProject]) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a new session runs a Codex-shaped turn through every state", async () => {
  const projectName = path.basename(project);
  await expect(page.getByRole("heading", { name: `What should we build in ${projectName}?` })).toBeVisible();
  // The agent chip fills in once the detector has probed; sending before
  // that would have nothing to launch.
  await expect(page.locator("[data-chip=agent]")).not.toContainText("Choose an agent");
  await expect(page.locator("[data-chip=git-mode]")).toBeVisible();
  await expect(page.locator("[data-chip=approval]")).toContainText("Ask");
  await shoot("session-new.png");

  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("showcase: write a greeting script and tidy up");
  await composer.press("Enter");

  // The session exists, the sidebar lists it under the project with a
  // spinner, and the title is the prompt.
  const view = page.locator("[data-session-view]");
  await expect(view).toBeVisible();
  const row = page.locator("[data-session-row]");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("showcase: write a greeting script and tidy up");
  await expect(page.locator("[data-session-title]")).toContainText("showcase: write a greeting script");

  // Streaming: the thought, the first activity rows, the status line, and
  // stop in place of send.
  await expect(page.locator("[data-activity-row], [data-activity-group]").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(page.locator("[data-status-line]")).toBeVisible();
  await shoot("session-streaming.png");

  // Waiting: the permission card with one action per option.
  const permission = page.locator("[data-permission][data-outcome=pending]");
  await expect(permission).toBeVisible();
  await expect(permission).toContainText("Delete the build directory?");
  await expect(permission.getByRole("button", { name: "Yes", exact: true })).toBeVisible();
  await expect(permission.getByRole("button", { name: "Yes, always" })).toBeVisible();
  await expect(permission.getByRole("button", { name: "No", exact: true })).toBeVisible();
  await expect(page.locator("[data-status-line]")).toContainText("Waiting for your approval");
  await expect(row).toHaveAttribute("data-status", "waiting");
  await shoot("session-permission.png");
  await permission.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.locator("[data-permission][data-outcome=selected]")).toContainText("Allowed");

  // Completed: prose, the folded rows, the subagent, the plan card, the
  // files-changed pill, the usage chip; send is back.
  await expect(view).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  await expect(page.getByText("the stale build directory is gone")).toBeVisible();
  await expect(page.locator("[data-subagent]")).toContainText("Docs checker finished");
  await expect(page.locator("[data-plan-card]")).toContainText("3 of 3 done");
  await expect(page.locator("[data-files-changed]")).toContainText("2 files changed");
  await expect(page.locator("[data-files-changed]")).toContainText("+8 −0");
  await expect(page.locator("[data-part=usage]")).toContainText("tokens");
  await expect(page.getByRole("button", { name: "Submit" })).toBeVisible();
  await expect(row).toHaveAttribute("data-status", "idle");
  await shoot("session-completed.png");

  // Folding: the consecutive reads, edits and commands are one line.
  const group = page.locator("[data-activity-group]").first();
  await expect(group).toContainText("Read 2 files, edited 2 files, ran 2 commands");
  await group.getByRole("button").first().click();
  const editRow = page.locator("[data-activity-row=sc-edit-1]");
  await expect(editRow).toContainText("Edited hello.py");
  await expect(editRow).toContainText("+6 −0");
  await editRow.getByRole("button").first().click();
  await expect(page.locator("[data-testid=diff-view]")).toBeVisible({ timeout: 20_000 });
  const execRow = page.locator("[data-activity-row=sc-exec-1]");
  await expect(execRow).toContainText("python hello.py");
  await execRow.getByRole("button").first().click();
  await expect(page.locator("[data-tool-detail]").filter({ hasText: "hello from the fake agent" }).last()).toBeVisible();
  await shoot("session-expanded.png");
});

test("stop cancels the running turn", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("slow");
  await composer.press("Enter");
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(page.locator("[data-turn][data-role=agent]").last()).toContainText("working");
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.locator("[data-stopped]")).toBeVisible();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
  await shoot("session-cancelled.png");
});

test("a queued prompt goes out when the turn ends", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("slow");
  await composer.press("Enter");
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await page.getByPlaceholder("Send another message — it goes next").fill("thought and then ok");
  await page.keyboard.press("Enter");
  await expect(page.getByText("1 queued prompt")).toBeVisible();
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByText("1 queued prompt")).toBeHidden();
  await expect(page.locator("[data-turn][data-role=user]").last()).toContainText("thought and then ok");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
});

test("a crashed agent is an inline error with retry, and reconnecting resumes the history", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("crash");
  await composer.press("Enter");
  await expect(page.locator("[data-part=error]")).toBeVisible();
  await expect(page.locator("[data-part=error]")).toContainText("exited");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.locator("[data-session-row]")).toHaveAttribute("data-status", "error");
  await shoot("session-error.png");

  await page.getByRole("button", { name: "Reconnect" }).click();
  // The fake's `session/load` replays one earlier exchange.
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
  await expect(page.locator("[data-turn][data-role=user]").first()).toContainText("earlier prompt");
  await expect(page.getByText("earlier reply")).toBeVisible();
  await shoot("session-resumed.png");
});

test("the sidebar renames and archives a session", async () => {
  const row = page.locator("[data-session-row]");
  await row.getByRole("button", { name: /actions$/ }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  const input = page.getByLabel("Session title");
  await input.fill("Greeting script");
  await input.press("Enter");
  await expect(row).toContainText("Greeting script");
  await expect(page.locator("[data-session-title]")).toContainText("Greeting script");

  await row.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Archive" }).click();
  await expect(row).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
});

test("a signed-out agent asks to sign in", async () => {
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), signedOutProject);
  await page.locator("[data-chip=project]").click();
  await page.getByRole("menuitemradio", { name: path.basename(signedOutProject) }).click();
  await expect(page.getByRole("heading", { name: `What should we build in ${path.basename(signedOutProject)}?` })).toBeVisible();
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("hello");
  await composer.press("Enter");
  const auth = page.locator("[data-auth-prompt]");
  await expect(auth).toBeVisible();
  await expect(auth).toContainText("Sign in to");
  await expect(auth.getByRole("button", { name: /Sign in/ })).toBeVisible();
  await expect(page.locator("[data-session-row]")).toHaveCount(0);
  await shoot("session-auth.png");
});

async function shoot(name: string) {
  await page.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}

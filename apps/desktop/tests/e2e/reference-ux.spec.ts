import fs from "node:fs";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

test("viewer context and revision requests stay with the right draft and workspace", async () => {
  const model = process.env.HARDCORE_E2E_CAD_MODEL;
  test.skip(!model || !process.env.CAD_DESKTOP_PYTHON, "set HARDCORE_E2E_CAD_MODEL to the toy car STEP and CAD_DESKTOP_PYTHON");
  test.setTimeout(180_000);
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-reference-ux-")));
  const project = path.join(base, "car-project");
  fs.mkdirSync(path.join(project, "models"), { recursive: true });
  fs.copyFileSync(model!, path.join(project, "models/car.step"));
  fs.writeFileSync(path.join(project, "models/car.py"), "WHEEL_WIDTH = 14\n");
  const git = (...args: string[]) => execFileSync("git", ["-C", project, ...args], { stdio: "pipe" });
  git("init");
  git("add", "models/car.py", "models/car.step");
  git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "Add car source");
  fs.writeFileSync(path.join(project, "models/car.py"), "WHEEL_WIDTH = 18\n");
  const app = await electron.launch({
    args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${path.join(base, "profile")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") },
  });
  try {
    const page = await app.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    await page.evaluate((root) => window.hardcore.settings.set({ theme: "dark", worktreeRoot: root }), path.join(base, "worktrees"));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1280, 800));
    const added = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), project);
    await expect(page.getByText(added.name).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();
    const session = await page.evaluate((projectId) => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "none" }), added.id);
    await page.locator(`[data-session-row="${session.id}"]`).getByRole("button").first().click();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+t" : "Control+t");
    await page.getByLabel("Filter files").fill("models/car.step");
    await page.getByRole("option", { name: "models/car.step", exact: false }).first().click();
    const wheel = page.getByRole("treeitem", { name: /Component wheel_front_left/ });
    await expect(wheel).toBeVisible({ timeout: 90_000 });
    await wheel.click();
    const tip = page.locator("[data-reference-tip]");
    await expect(tip).toBeVisible();
    // The popover portals to body, but its collision boundary is the CAD surface.
    await expect.poll(async () => {
      const hint = await tip.boundingBox();
      const surface = await page.locator("[data-cad-surface]").boundingBox();
      return !!hint && !!surface && hint.x >= surface.x && hint.x + hint.width <= surface.x + surface.width;
    }).toBe(true);
    await page.screenshot({ path: test.info().outputPath("contained-reference-tip.png"), animations: "disabled" });
    await page.keyboard.press("Escape");
    await expect(tip).toHaveCount(0);
    await expect(wheel).toHaveAttribute("aria-selected", "true");

    const draft = page.getByPlaceholder("Do anything");
    await draft.fill("Make this wheel wider: ");
    await wheel.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Copy Reference", exact: true }).click();
    const chip = page.locator("[data-composer] [data-reference-chip]");
    await expect(chip).toHaveCount(0);
    await expect(draft).toHaveText("Make this wheel wider:");
    await page.getByRole("button", { name: "Add to prompt", exact: true }).click();
    await expect(draft).toBeFocused();
    await expect(chip).toHaveText("wheel_front_left");
    await wheel.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Add to prompt", exact: true }).click();
    await expect(chip).toHaveCount(1);
    await expect(draft).toBeFocused();
    const selector = await chip.getAttribute("data-selector");
    const token = `models/car.step#${selector}`;
    await expect(chip).toHaveAttribute("title", `Show ${token} in viewer`);
    await page.getByRole("button", { name: "Close car.step", exact: true }).click();
    await chip.getByRole("button").click();
    await expect(wheel).toHaveAttribute("aria-selected", "true");
    await expect(tip).toHaveCount(0);
    await expect(chip).toHaveText("wheel_front_left");
    await page.mouse.move(350, 80);
    await page.screenshot({ path: test.info().outputPath("named-wheel-reference.png"), animations: "disabled" });
    await page.locator("[data-composer]").getByRole("button", { name: "Add to this prompt" }).click();
    await page.getByRole("menuitem", { name: "Ask about this view" }).click();
    await expect(page.locator("[data-composer]").getByText(/car-.*\.png/)).toHaveCount(1);
    await expect(chip).toHaveCount(1);
    await expect(draft).toBeFocused();
    await draft.press("Enter");
    await expect.poll(async () => {
      const state = await page.evaluate((id) => window.hardcore.sessions.state({ id }), session.id);
      return state?.turns.find((turn) => turn.role === "user")?.parts.find((part) => part.type === "text");
    }).toMatchObject({ type: "text", text: `Make this wheel wider: ${token}` });
    const submitted = await page.evaluate((id) => window.hardcore.sessions.state({ id }), session.id);
    expect(submitted?.turns.find((turn) => turn.role === "user")?.parts.some((part) => part.type === "image")).toBe(true);
    await page.keyboard.press(process.platform === "darwin" ? "Meta+Shift+r" : "Control+Shift+r");
    const revision = page.getByRole("button", { name: "Request revision for models/car.py", exact: true });
    await expect(revision).toBeVisible();
    await draft.fill("Keep the wheel centered.");
    await revision.click();
    await expect(draft).toContainText("Keep the wheel centered.");
    await expect(draft).toContainText("Please revise models/car.py (All changes).");
    await expect(draft).toBeFocused();
    await page.screenshot({ path: test.info().outputPath("request-revision.png"), animations: "disabled" });
    // Select changed code in the actual Monaco editor, then carry it into the draft.
    const code = page.locator(".monaco-diff-editor .modified .view-line").filter({ hasText: "WHEEL_WIDTH = 18" }).first();
    await code.click({ clickCount: 3 });
    await expect(page.locator(".monaco-diff-editor .modified .selected-text").first()).toBeVisible();
    await revision.click();
    await expect(draft).toContainText("Selected modified lines");
    await expect(draft).toContainText("WHEEL_WIDTH = 18");
    await expect(draft).toBeFocused();
    await page.screenshot({ path: test.info().outputPath("revision-with-selection.png"), animations: "disabled" });
    const other = await page.evaluate((projectId) => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "worktree", name: "Other workspace" }), added.id);
    await page.locator(`[data-session-row="${other.id}"]`).getByRole("button").first().click();
    await draft.fill("Preserve my other workspace draft.");
    await page.getByRole("tab", { name: /car.step/ }).click();
    await expect(wheel).toBeVisible();
    if (await wheel.getAttribute("aria-selected") !== "true") await wheel.click();
    await expect(wheel).toHaveAttribute("aria-selected", "true");
    await page.getByTestId("capture-to-chat").click();
    const startHere = page.getByRole("button", { name: "Start chat here", exact: true });
    await expect(startHere).toBeVisible();
    await expect(draft).toHaveText("Preserve my other workspace draft.");
    await startHere.click();
    await expect(chip).toHaveText("wheel_front_left");
    await expect(page.locator("[data-composer]").getByText(/car-.*\.png/)).toHaveCount(1);
    await expect(draft).toBeFocused();
    const sessions = await page.evaluate((projectId) => window.hardcore.sessions.list({ projectId }), added.id);
    const created = sessions.find((item) => item.id !== session.id && item.id !== other.id);
    expect(created?.cwd).toBe(project);
    expect((await page.evaluate((id) => window.hardcore.sessions.state({ id }), created!.id))?.turns).toHaveLength(0);
    await page.screenshot({ path: test.info().outputPath("view-in-correct-workspace.png"), animations: "disabled" });
    await page.locator(`[data-session-row="${other.id}"]`).getByRole("button").first().click();
    await expect(draft).toHaveText("Preserve my other workspace draft.");
  } catch (error) {
    await app.windows()[0]?.screenshot({ path: test.info().outputPath("failure.png") }).catch(() => {});
    throw error;
  } finally {
    await app.close();
    fs.rmSync(base, { recursive: true, force: true });
  }
});

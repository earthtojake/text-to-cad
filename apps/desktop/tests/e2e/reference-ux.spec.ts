import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

test("named wheel references preserve their token and the hint stays inside the viewer", async () => {
  const model = process.env.HARDCORE_E2E_CAD_MODEL;
  test.skip(!model || !process.env.CAD_DESKTOP_PYTHON, "set HARDCORE_E2E_CAD_MODEL to the toy car STEP and CAD_DESKTOP_PYTHON");
  test.setTimeout(180_000);
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-reference-ux-"));
  const project = path.join(base, "car-project");
  fs.mkdirSync(path.join(project, "models"), { recursive: true });
  fs.copyFileSync(model!, path.join(project, "models/car.step"));
  const app = await electron.launch({
    args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${path.join(base, "profile")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") },
  });
  try {
    const page = await app.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1280, 800));
    const added = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), project);
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
    await expect(chip).toHaveText("wheel_front_left");
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
    await draft.press("Enter");
    await expect.poll(async () => {
      const state = await page.evaluate((id) => window.hardcore.sessions.state({ id }), session.id);
      return state?.turns.find((turn) => turn.role === "user")?.parts.find((part) => part.type === "text");
    }).toMatchObject({ type: "text", text: `Make this wheel wider: ${token}` });
  } finally {
    await app.close();
    fs.rmSync(base, { recursive: true, force: true });
  }
});

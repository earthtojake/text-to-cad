import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

for (const agentId of ["codex", "claude-code"]) {
  test(`${agentId} car generation, reference edit and native handoff`, async () => {
    const testInfo = test.info();
    const source = process.env.HARDCORE_E2E_CAD_SOURCE;
    const python = process.env.CAD_DESKTOP_PYTHON;
    test.skip(process.env.HARDCORE_E2E_LIVE_CAD !== "1" || !source || !python, "set HARDCORE_E2E_LIVE_CAD, HARDCORE_E2E_CAD_SOURCE and CAD_DESKTOP_PYTHON");
    test.setTimeout(360_000);
    const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-car-handoff-")));
    const project = path.join(base, "project");
    fs.mkdirSync(path.join(project, "models"), { recursive: true });
    fs.copyFileSync(source!, path.join(project, "models/car.py"));
    fs.writeFileSync(path.join(project, "AGENTS.md"), "Isolated integration test. Do only requested operations in this workspace. Do not update memory or inspect unrelated projects.\n");
    const git = (...args: string[]) => execFileSync("git", args, { cwd: project, stdio: "ignore" });
    git("init", "-q");
    git("add", ".");
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "car fixture");
    const profile = path.join(base, "profile");
    const launch = () => electron.launch({
      args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${profile}`],
      env: { ...process.env, NODE_ENV: "test" },
    });
    let app = await launch();
    try {
      let page = await app.firstWindow();
      await page.waitForLoadState("domcontentloaded");
      await page.evaluate((root) => window.hardcore.settings.set({ worktreeRoot: root, fetchBeforeCreate: false }), path.join(base, "worktrees"));
      const added = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), project);
      const session = await page.evaluate(({ projectId, agentId }) => window.hardcore.sessions.create({ projectId, agentId, gitMode: "worktree", name: "car-ux-check" }), { projectId: added.id, agentId });
      await page.evaluate((id) => window.hardcore.sessions.setApprovalMode({ id, mode: "approve-for-me" }), session.id);
      await page.locator(`[data-session-row="${session.id}"]`).getByRole("button").first().click();
      for (const directory of [".agents", ".claude"]) {
        const skills = path.join(session.cwd, directory, "skills", "hardcore-app-use");
        fs.mkdirSync(skills, { recursive: true });
        fs.copyFileSync(path.join(appRoot, "skills/hardcore-app-use/SKILL.md"), path.join(skills, "SKILL.md"));
      }
      const state = await page.evaluate((id) => window.hardcore.sessions.state({ id }), session.id);
      const model = state?.configOptions.find((option) => option.id === "model" && option.type === "select");
      if (model?.type === "select") {
        const choice = model.options.find((option) => /sonnet|gpt-5\.4/.test(option.value));
        if (choice) await page.evaluate(({ id, value }) => window.hardcore.sessions.setConfigOption({ id, configId: "model", value }), { id: session.id, value: choice.value });
      }
      // This UX test explicitly supplies the developer runtime; runtime provisioning
      // and performance are owned separately. Never let the agent hunt other installs.
      const build = `PYTHONPATH=${JSON.stringify(path.resolve(appRoot, "../../packages/cadgen/src"))} ${JSON.stringify(python)} models/car.py`;
      const marker = `CAR_HANDOFF_${agentId.replaceAll("-", "_")}`;
      const draft = page.getByPlaceholder("Do anything");
      await draft.fill(`Remember ${marker} as this conversation's verification marker. Read the local hardcore-app-use skill. Build models/car.py by running exactly: ${build}. Do not change its dimensions. Open models/car.step using the Hardcore open_file tool. Do not start another viewer. Reply briefly.`);
      await draft.press("Enter");
      await expect(page.getByRole("tab", { name: /car\.step/ })).toBeVisible({ timeout: 150_000 });
      await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 90_000 });
      await expect(page.locator("canvas").first()).toBeVisible({ timeout: 90_000 });
      await expect(page.getByRole("treeitem", { name: /Component chassis_body/ })).toBeVisible({ timeout: 60_000 });
      await draft.fill("Make the wheels wider: change WHEEL_WIDTH from 14.0 to 18.0, keeping the other dimensions. One wheel is ");
      const wheel = page.getByRole("treeitem", { name: /Component wheel_front_left/ });
      await wheel.click({ button: "right" });
      await page.getByRole("menuitem", { name: "Add to prompt", exact: true }).click();
      const chip = page.locator("[data-composer] [data-reference-chip]");
      await expect(chip).toHaveCount(1);
      await expect(chip).toHaveAttribute("data-file", "models/car.step");
      await expect(draft).toContainText("Make the wheels wider");
      // Return to the copied wheel after inspecting a different part. Clicking
      // the chip must not send the prompt or replace any of its words.
      await page.getByRole("treeitem", { name: /Component chassis_body/ }).click();
      await chip.getByRole("button").click();
      await expect(wheel).toHaveAttribute("aria-selected", "true");
      await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
      await expect(draft).toContainText("Make the wheels wider");
      // Closing the model and activating by keyboard reopens the same worktree
      // and selects the wheel, without submitting the draft.
      await page.getByRole("button", { name: "Close car.step", exact: true }).click();
      await chip.getByRole("button").focus();
      await chip.getByRole("button").press("Enter");
      await expect(wheel).toHaveAttribute("aria-selected", "true");
      await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
      await draft.press("End");
      await page.keyboard.type(` Rebuild with the same command and open the updated STEP.`);
      await page.screenshot({ path: testInfo.outputPath("car-reference.png") });
      await draft.press("Enter");
      await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "running", { timeout: 15_000 });
      await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 150_000 });
      expect(fs.readFileSync(path.join(session.cwd, "models/car.py"), "utf8")).toContain("WHEEL_WIDTH = 18.0");
      expect(fs.readFileSync(path.join(project, "models/car.py"), "utf8")).toContain("WHEEL_WIDTH = 14.0");
      await page.screenshot({ path: testInfo.outputPath("car-edited.png") });
      await page.evaluate((id) => window.hardcore.sessions.close({ id }), session.id);
      await app.close();
      app = await launch();
      page = await app.firstWindow();
      await page.waitForLoadState("domcontentloaded");
      const replay = await page.evaluate((id) => window.hardcore.sessions.load({ id }), session.id);
      expect(JSON.stringify(replay.turns)).toContain(marker);
      const tabs = await page.evaluate((projectId) => window.hardcore.explorer.loadTabs({ projectId }), added.id);
      expect(tabs.some((tab) => tab.kind === "file" && tab.path === "models/car.step" && tab.root === session.cwd)).toBe(true);
      const record = { agentId, acpSessionId: session.acpSessionId, cwd: session.cwd, marker, base };
      await testInfo.attach("native-handoff", { body: JSON.stringify(record), contentType: "application/json" });
      if (process.env.HARDCORE_E2E_HANDOFF_DIR) {
        fs.mkdirSync(process.env.HARDCORE_E2E_HANDOFF_DIR, { recursive: true });
        fs.writeFileSync(path.join(process.env.HARDCORE_E2E_HANDOFF_DIR, `${agentId}.json`), JSON.stringify(record));
      }
    } finally {
      await app.close();
      if (!process.env.HARDCORE_E2E_HANDOFF_DIR) fs.rmSync(base, { recursive: true, force: true });
    }
  });
}

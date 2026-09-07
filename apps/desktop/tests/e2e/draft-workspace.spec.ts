import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

for (const scenario of ["project drafts", "new worktree"]) {
  test(scenario, async () => {
    test.setTimeout(60_000);
    const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-draft-")));
    const project = path.join(base, "Car project");
    const other = path.join(base, "Other project");
    fs.mkdirSync(project);
    fs.mkdirSync(other);
    const git = (...args: string[]) => execFileSync("git", args, { cwd: project, stdio: "ignore" });
    git("init", "-q");
    fs.writeFileSync(path.join(project, "README.md"), "Draft workspace fixture\n");
    git("add", "README.md");
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture");
    const app = await electron.launch({
      args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${path.join(base, "profile")}`],
      env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") },
    });
    try {
      const page = await app.firstWindow();
      await page.waitForLoadState("domcontentloaded");
      await page.evaluate((root) => window.hardcore.settings.set({ worktreeRoot: root, fetchBeforeCreate: false }), path.join(base, "worktrees"));
      const added = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), project);
      const draft = page.getByPlaceholder("Do anything");
      await expect(draft).toBeVisible();
      if (scenario === "project drafts") {
        await draft.fill("Round the car body");
        await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), other);
        await page.getByRole("button", { name: "Other project", exact: true }).first().click();
        await expect(page.getByRole("heading", { name: "What should we build in Other project?" })).toBeVisible();
        await expect(draft).toHaveText("");
        await page.getByRole("button", { name: "Car project", exact: true }).first().click();
        await expect(draft).toHaveText("Round the car body");
      } else {
        await page.locator("[data-context-strip]").getByRole("button", { name: "Local", exact: true }).click();
        await page.getByRole("menuitemradio", { name: /New worktree/ }).click();
        await expect(page.locator("[data-context-strip]").getByRole("button", { name: "Claude Code", exact: true })).toBeVisible({ timeout: 30_000 });
        await draft.fill("write a file");
        await draft.press("Enter");
        await expect(page.locator("[data-session-view]")).toBeVisible({ timeout: 30_000 });
        const sessions = await page.evaluate((projectId) => window.hardcore.sessions.list({ projectId }), added.id);
        expect(sessions[0]?.cwd).not.toBe(project);
        expect(sessions[0]?.worktreePath).toBe(sessions[0]?.cwd);
      }
    } finally {
      await app.close();
      fs.rmSync(base, { recursive: true, force: true });
    }
  });
}

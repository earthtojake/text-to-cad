import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

test("activity keeps failures separate from the summary and uses a quiet thinking icon", async () => {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-activity-feedback-")));
  const project = path.join(base, "project");
  fs.mkdirSync(path.join(project, "models"), { recursive: true });
  fs.writeFileSync(path.join(project, "README.md"), "# Preview project\n");
  const app = await electron.launch({
    args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${path.join(base, "profile")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") },
  });
  try {
    const page = await app.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1280, 800));
    const added = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), project);
    await expect(page.getByText(added.name).first()).toBeVisible();
    const session = await page.evaluate((projectId) => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "none" }), added.id);
    await page.locator(`[data-session-row="${session.id}"]`).getByRole("button").first().click();
    // The read and echo succeed. Writing to an existing directory fails safely.
    await page.evaluate(({ id, text }) => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text }] }), { id: session.id, text: `thought read ${path.join(project, "README.md")} write ${path.join(project, "models")} terminal` });
    const group = page.locator("[data-activity-group]");
    const summary = group.getByRole("button").first();
    await expect(summary).toContainText("1 failed");
    await expect(summary).not.toHaveClass(/text-destructive/);
    await expect(group.locator("[data-activity-failures]")).toHaveText("1 failed");
    const thought = page.getByRole("button", { name: /^Thought/ });
    await expect(thought.locator("svg.lucide-ellipsis")).toBeVisible();
    await expect(thought.locator("svg.lucide-sparkles")).toHaveCount(0);
    await page.screenshot({ path: test.info().outputPath("activity-collapsed-light.png"), animations: "disabled" });
    await summary.click();
    const failedRow = page.locator('[data-activity-row][data-status="failed"]');
    await expect(failedRow.getByRole("button")).toContainText("Failed");
    await failedRow.getByRole("button").click();
    await expect(failedRow.locator("[data-tool-detail]")).toContainText(/EISDIR|directory/i);
    await page.screenshot({ path: test.info().outputPath("activity-expanded-light.png"), animations: "disabled" });
    await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
    await summary.click();
    await page.screenshot({ path: test.info().outputPath("activity-collapsed-dark.png"), animations: "disabled" });
  } finally {
    await app.close();
    fs.rmSync(base, { recursive: true, force: true });
  }
});

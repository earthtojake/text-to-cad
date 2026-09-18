import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    sessions: {
      create(input: { projectId: string; agentId: string; gitMode: "none" }): Promise<{ id: string }>;
      prompt(input: { id: string; content: Array<{ type: "text"; text: string }> }): Promise<unknown>;
      get(input: { id: string }): Promise<{ id: string; title: string; titleSource: string } | null>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

async function launch(userData: string): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_E2E_HIDDEN: "1", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  const page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  return { app, page };
}

async function agentTitle(page: Page, id: string, title: string): Promise<void> {
  await page.evaluate(
    ({ id, title }) => window.hardcore.sessions.prompt({
      id,
      content: [{ type: "text", text: `session-title ${JSON.stringify({ title })}` }],
    }),
    { id, title },
  );
}

test("agent titles update the sidebar and header, survive restart, and respect manual renames", async () => {
  test.setTimeout(120_000);
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-titles-"));
  const userData = path.join(scratch, "profile");
  const project = path.join(scratch, "project");
  fs.mkdirSync(project);
  let current: Awaited<ReturnType<typeof launch>> | null = null;
  try {
    current = await launch(userData);
    const id = await current.page.evaluate(async (directory) => {
      const project = await window.hardcore.projects.addPath({ path: directory });
      const session = await window.hardcore.sessions.create({ projectId: project.id, agentId: "claude-code", gitMode: "none" });
      return session.id;
    }, project);
    await current.page.locator("[data-session-row]").click();
    await expect(current.page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    await agentTitle(current.page, id, "Design the gripper");
    await expect(current.page.locator("[data-session-row]")).toContainText("Design the gripper");
    await expect(current.page.locator("[data-session-title]")).toHaveText("Design the gripper");

    await current.app.close();
    current = await launch(userData);
    await expect(current.page.locator("[data-session-row]")).toContainText("Design the gripper");
    await current.page.locator("[data-session-row]").click();
    await expect(current.page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    await expect(current.page.locator("[data-session-title]")).toHaveText("Design the gripper");
    expect(await current.page.evaluate((id) => window.hardcore.sessions.get({ id }), id)).toMatchObject({
      title: "Design the gripper", titleSource: "agent",
    });

    // Exercise the actual inline title editor, then a later agent notification.
    await current.page.locator("[data-session-title]").click();
    const editor = current.page.locator("[data-session-header]").getByRole("textbox", { name: "Session title" });
    await editor.fill("My gripper task");
    await editor.press("Enter");
    await expect.poll(() => current!.page.evaluate((id) => window.hardcore.sessions.get({ id }), id))
      .toMatchObject({ title: "My gripper task", titleSource: "user" });
    await agentTitle(current.page, id, "Agent replacement title");
    await expect(current.page.locator("[data-session-title]")).toHaveText("My gripper task");
    await expect(current.page.locator("[data-session-row]")).toContainText("My gripper task");

    await current.app.close();
    current = await launch(userData);
    await current.page.locator("[data-session-row]").click();
    await expect(current.page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    await agentTitle(current.page, id, "Another agent title");
    await expect(current.page.locator("[data-session-title]")).toHaveText("My gripper task");
    await expect(current.page.locator("[data-session-row]")).toContainText("My gripper task");
  } finally {
    await current?.app.close();
    fs.rmSync(scratch, { recursive: true, force: true });
  }
});

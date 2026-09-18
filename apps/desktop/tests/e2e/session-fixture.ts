import { expect, type Page } from "@playwright/test";

declare const window: {
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string }> };
    sessions: {
      create(request: { projectId: string; agentId: string; gitMode: "none" }): Promise<{ id: string }>;
      rename(request: { id: string; title: string }): Promise<unknown>;
    };
  };
};

type FixtureSession = { id: string; projectId: string; title: string };
const sessions = new WeakMap<Page, Map<string, FixtureSession>>();

/** A real selected session owns each fixture's explorer; choosing a folder alone does not. */
export async function selectFixtureSession(page: Page, directory: string): Promise<FixtureSession> {
  let byDirectory = sessions.get(page);
  if (!byDirectory) {
    byDirectory = new Map();
    sessions.set(page, byDirectory);
  }
  let session = byDirectory.get(directory);
  if (!session) {
    session = await page.evaluate(async (directory) => {
      const project = await window.hardcore.projects.addPath({ path: directory });
      const session = await window.hardcore.sessions.create({ projectId: project.id, agentId: "claude-code", gitMode: "none" });
      const title = `Fixture ${session.id.slice(0, 8)}`;
      await window.hardcore.sessions.rename({ id: session.id, title });
      return { id: session.id, projectId: project.id, title };
    }, directory);
    byDirectory.set(directory, session);
  }
  if (!(await page.getByTestId("sidebar").isVisible())) {
    await page.getByRole("button", { name: "Toggle sidebar" }).click();
  }
  await page.getByTestId("sidebar").getByRole("button", { name: session.title, exact: true }).click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  return session;
}

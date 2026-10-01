/**
 * Settings › General › "Where the Open folder chooser opens" has to reach the
 * native chooser: `projects.add` passes it as `defaultPath` when the folder is
 * still there, and passes nothing when it is not.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const state = vi.hoisted(() => ({
  stored: { defaultProjectFolder: null as string | null },
  registered: null as null | { projects: { add: (request: void, ctx: object) => Promise<unknown> } },
  showOpenDialog: vi.fn(),
}));

vi.mock("electron", () => ({
  BrowserWindow: { fromWebContents: () => null },
  app: { isPackaged: false },
  dialog: { showOpenDialog: state.showOpenDialog },
  shell: {},
}));
vi.mock("@main/db/repositories", () => ({
  projects: {},
  settings: { get: () => ({ ...state.stored }) },
}));
vi.mock("@main/cad", () => ({ viewers: () => ({}) }));
vi.mock("@main/telemetry", () => ({ changedSettingsKeys: () => [], track: () => {} }));
vi.mock("@main/settings-effects", () => ({ applySettingsEffects: () => {} }));
vi.mock("@main/ipc/register", () => ({
  IpcError: class extends Error {},
  broadcast: () => {},
  registerIpc: (_contract: unknown, handlers: typeof state.registered) => {
    state.registered = handlers;
  },
}));
vi.mock("@main/ipc/runtime", () => ({ refreshRuntimeAfterOverride: () => {}, runtimeHandlers: {} }));
vi.mock("@main/ipc/explorer", () => ({ explorerHandlers: {}, initExplorerServices: () => {}, revealProjectDirectory: () => {} }));
vi.mock("@main/ipc/acp", () => ({ acpHandlers: {} }));
vi.mock("@main/ipc/agent-options", () => ({ agentOptionsHandlers: {} }));
vi.mock("@main/ipc/agents", () => ({ agentsHandlers: {} }));
vi.mock("@main/ipc/app", () => ({ appHandlers: {} }));
vi.mock("@main/ipc/integrations", () => ({ integrationHandlers: {} }));
vi.mock("@main/ipc/cad", () => ({ cadHandlers: {} }));
vi.mock("@main/ipc/clipboard", () => ({ clipboardHandlers: {} }));
vi.mock("@main/ipc/browser", () => ({ browserHandlers: {} }));
// `existingPath` is the rule under test, so it stays real; the handlers are not needed.
vi.mock(import("@main/ipc/dialogs"), async (importOriginal) => ({ ...(await importOriginal()), dialogsHandlers: {} as never }));
vi.mock("@main/ipc/git", () => ({ gitHandlers: {} }));
vi.mock("@main/ipc/onboarding", () => ({ onboardingHandlers: {} }));
vi.mock("@main/ipc/skills", () => ({ skillsHandlers: {} }));
import { registerIpcHandlers } from "@main/ipc";

let folder: string;

async function openChooser(): Promise<Record<string, unknown>> {
  if (!state.registered) {
    registerIpcHandlers();
  }
  await state.registered!.projects.add(undefined, { sender: {} });
  return state.showOpenDialog.mock.calls[0]!.at(-1) as Record<string, unknown>;
}

beforeEach(() => {
  folder = mkdtempSync(path.join(tmpdir(), "open-folder-default-"));
  state.showOpenDialog.mockReset().mockResolvedValue({ canceled: true, filePaths: [] });
});

afterEach(() => rmSync(folder, { recursive: true, force: true }));

test("the stored default folder is where the chooser opens", async () => {
  state.stored = { defaultProjectFolder: folder };
  expect(await openChooser()).toMatchObject({ defaultPath: folder });
});

test("a default folder that is gone is left out", async () => {
  state.stored = { defaultProjectFolder: path.join(folder, "missing") };
  expect(await openChooser()).not.toHaveProperty("defaultPath");
});

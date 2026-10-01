/**
 * `settings.set` is where an interpreter override change reaches the runtime:
 * a changed `cadPythonOverride` stops every viewer and re-probes (so About and
 * a CAD tab stop quoting the old interpreter); any other setting does neither.
 * The handler is taken from what `registerIpcHandlers` registers, so this is
 * the wiring the app runs, not a copy of it.
 */
import { beforeEach, expect, test, vi } from "vitest";

const state = vi.hoisted(() => ({
  stored: { cadPythonOverride: null as string | null, theme: "system" },
  registered: null as null | { settings: { set: (patch: object) => unknown } },
  refresh: vi.fn(),
  stopAll: vi.fn(),
}));

vi.mock("electron", () => ({ BrowserWindow: {}, app: { isPackaged: false }, dialog: {}, shell: {} }));
vi.mock("@main/db/repositories", () => ({
  projects: {},
  settings: {
    get: () => ({ ...state.stored }),
    set: (patch: object) => {
      state.stored = { ...state.stored, ...patch };
      return { ...state.stored };
    },
  },
}));
vi.mock("@main/cad", () => ({ viewers: () => ({ stopAll: state.stopAll }) }));
vi.mock("@main/telemetry", () => ({ changedSettingsKeys: () => [], track: () => {} }));
vi.mock("@main/settings-effects", () => ({ applySettingsEffects: () => {} }));
vi.mock("@main/ipc/register", () => ({
  IpcError: class extends Error {},
  broadcast: () => {},
  registerIpc: (_contract: unknown, handlers: typeof state.registered) => {
    state.registered = handlers;
  },
}));
vi.mock("@main/ipc/runtime", () => ({ refreshRuntimeAfterOverride: state.refresh, runtimeHandlers: {} }));
vi.mock("@main/ipc/explorer", () => ({ explorerHandlers: {}, initExplorerServices: () => {}, revealProjectDirectory: () => {} }));
vi.mock("@main/ipc/acp", () => ({ acpHandlers: {} }));
vi.mock("@main/ipc/agent-options", () => ({ agentOptionsHandlers: {} }));
vi.mock("@main/ipc/agents", () => ({ agentsHandlers: {} }));
vi.mock("@main/ipc/app", () => ({ appHandlers: {} }));
vi.mock("@main/ipc/integrations", () => ({ integrationHandlers: {} }));
vi.mock("@main/ipc/cad", () => ({ cadHandlers: {} }));
vi.mock("@main/ipc/clipboard", () => ({ clipboardHandlers: {} }));
vi.mock("@main/ipc/browser", () => ({ browserHandlers: {} }));
vi.mock("@main/ipc/dialogs", () => ({ dialogsHandlers: {} }));
vi.mock("@main/ipc/git", () => ({ gitHandlers: {} }));
vi.mock("@main/ipc/onboarding", () => ({ onboardingHandlers: {} }));
vi.mock("@main/ipc/skills", () => ({ skillsHandlers: {} }));
import { registerIpcHandlers } from "@main/ipc";

function set(patch: object): unknown {
  if (!state.registered) {
    registerIpcHandlers();
  }
  return state.registered!.settings.set(patch);
}

beforeEach(() => {
  state.stored = { cadPythonOverride: null, theme: "system" };
  state.refresh.mockReset().mockResolvedValue({ state: "ready" });
  state.stopAll.mockReset();
});

test("a changed interpreter override stops the viewers and re-probes the runtime", () => {
  set({ cadPythonOverride: "/new/python" });
  expect(state.stopAll).toHaveBeenCalledOnce();
  expect(state.refresh).toHaveBeenCalledOnce();
});

test("another setting, or the override restated, re-probes nothing", () => {
  set({ theme: "dark" });
  state.stored.cadPythonOverride = "/same/python";
  set({ cadPythonOverride: "/same/python" });
  expect(state.stopAll).not.toHaveBeenCalled();
  expect(state.refresh).not.toHaveBeenCalled();
});

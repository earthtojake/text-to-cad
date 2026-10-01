/**
 * `sessions.archive` changes the row before it tears the session down, the way
 * `delete` does: an archive that throws leaves the session active with its
 * tokens, browser pages and shells, not half undone. The handler is the one
 * the app registers; only what it calls is stood in for.
 */
import { beforeEach, expect, test, vi } from "vitest";

const calls = vi.hoisted(() => ({
  archive: vi.fn(),
  forgetSession: vi.fn(),
  disposePages: vi.fn(),
  disposeShells: vi.fn(),
  forgetCad: vi.fn(),
}));

vi.stubGlobal("__APP_VERSION__", "0.0.0");
vi.mock("electron", () => ({ app: { isPackaged: false, getVersion: () => "0.0.0" } }));
vi.mock("@main/ipc/register", () => ({ IpcError: class extends Error {}, broadcast: () => {} }));
vi.mock("@main/ipc/agents", () => ({ detector: {} }));
vi.mock("@main/acp/pty-backend", () => ({ spawnPtyTerminal: () => {} }));
vi.mock("@main/acp/agent-options", () => ({ AgentOptionStore: class {} }));
vi.mock("@main/acp/sessions", () => ({ SessionManager: class { archive = calls.archive; } }));
vi.mock("@main/integrations", () => ({ forgetSession: calls.forgetSession, mcpServersFor: () => [], sessionPreamble: () => null, skillsRoot: () => null }));
vi.mock("@main/cad", () => ({ forgetCadSession: calls.forgetCad, sessionRuntimePath: () => [] }));
vi.mock("@main/telemetry", () => ({ track: () => {} }));
vi.mock("@main/db/repositories", () => ({ agentOptions: {}, projects: {}, sessions: {}, sessionStates: {}, settings: {} }));
vi.mock("@main/projects/git", () => ({ emptyTreeIfUnborn: () => {}, head: () => {}, isUnder: () => false, samePath: () => false }));
vi.mock("@main/projects/workspace", () => ({ releaseWorkspace: () => {} }));
vi.mock("@main/ipc/git", () => ({ sessionWorkspace: () => {}, sessionWorkspaceSettled: () => {} }));
vi.mock("@main/browser/service", () => ({ browserService: { disposeSession: calls.disposePages } }));
vi.mock("@main/browser/storage", () => ({ clearBrowserSessionStorage: () => {} }));
vi.mock("@main/ipc/explorer", () => ({ explorerTerminals: () => ({ disposeSession: calls.disposeShells }) }));
import { acpHandlers } from "@main/ipc/acp";

const archive = acpHandlers.sessions.archive as (input: { id: string; archived: boolean }) => Promise<unknown>;

beforeEach(() => {
  for (const fn of Object.values(calls)) fn.mockReset();
});

test("an archive that throws leaves the session's tokens, pages and shells alone", async () => {
  calls.archive.mockImplementation(() => { throw new Error("database is locked"); });
  await expect(archive({ id: "s", archived: true })).rejects.toThrow("database is locked");
  expect(calls.forgetSession).not.toHaveBeenCalled();
  expect(calls.disposePages).not.toHaveBeenCalled();
  expect(calls.disposeShells).not.toHaveBeenCalled();
});

test("an archive that lands tears the session's tools down; an unarchive does not", async () => {
  calls.archive.mockReturnValue({ id: "s" });
  await archive({ id: "s", archived: true });
  expect(calls.forgetSession).toHaveBeenCalledWith("s");
  expect(calls.disposePages).toHaveBeenCalledWith("s");
  expect(calls.disposeShells).toHaveBeenCalledWith("s");
  calls.forgetSession.mockClear();
  calls.forgetCad.mockClear();
  await archive({ id: "s", archived: false });
  expect(calls.forgetSession).not.toHaveBeenCalled();
  expect(calls.forgetCad).not.toHaveBeenCalled();
});

test("an archive stops the CAD viewer of the session's worktree; a session without one has none to stop", async () => {
  calls.archive.mockReturnValue({ id: "s", worktreePath: "/wt" });
  await archive({ id: "s", archived: true });
  expect(calls.forgetCad).toHaveBeenCalledWith("s", "/wt");
  calls.forgetCad.mockClear();
  calls.archive.mockReturnValue({ id: "s" });
  await archive({ id: "s", archived: true });
  expect(calls.forgetCad).toHaveBeenCalledWith("s", null);
});

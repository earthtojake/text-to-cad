/**
 * A row the last launch left (`probing`) is provisional: its "signed out" is
 * drawn as "Checking…", not as a verdict, and the store says a table is still
 * being confirmed until `agents.status` replaces it.
 */
import { expect, it, vi } from "vitest";

import { authLabel } from "@renderer/features/settings/AgentDrawer";
import { useAgents } from "@renderer/state/agents";
import type { AgentStatus } from "@shared/agents";

it("does not call a provisional row signed out", () => {
  expect(authLabel({ auth: "unauthenticated", installed: true })).toBe("Not signed in");
  expect(authLabel({ auth: "unauthenticated", installed: true, probing: true })).toBe("Checking…");
  expect(authLabel({ auth: "authenticated", installed: true, probing: true })).toBe("Signed in");
});

it("holds the probing mark until the fresh table replaces the table", () => {
  const row = { id: "claude-code", installed: true, launchWithoutBinary: true, auth: "unauthenticated", probing: true } as AgentStatus;
  useAgents.getState().receive([row]);
  expect(useAgents.getState().agents.some((agent) => agent.probing)).toBe(true);
  useAgents.getState().receive([{ ...row, auth: "authenticated", probing: undefined }]);
  expect(useAgents.getState().agents.some((agent) => agent.probing)).toBe(false);
});

it("reads a failed probe's flagged rows as a check that did not happen, not as agents signed out", () => {
  const row = { id: "claude-code", installed: true, launchWithoutBinary: true, auth: "unauthenticated", probeFailed: true } as AgentStatus;
  useAgents.getState().receive([row]);
  expect(useAgents.getState().loadError).not.toBeNull();
  useAgents.getState().receive([{ ...row, probeFailed: undefined }]);
  expect(useAgents.getState().loadError).toBeNull();
});

it("reads the flagged rows a cold probe's failure answers agents.list with as a failure, not as ready and fine", async () => {
  const row = { id: "claude-code", installed: false, launchWithoutBinary: true, auth: "unknown", probeFailed: true } as AgentStatus;
  const agentsApi = window.textToCad.agents as unknown as Record<string, unknown>;
  agentsApi.list = vi.fn(async () => [row]);
  useAgents.setState({ agents: [], ready: false, loadError: null });
  await useAgents.getState().load();
  expect(useAgents.getState().ready).toBe(true);
  expect(useAgents.getState().loadError).not.toBeNull();
});

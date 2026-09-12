import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  useAgentOptions,
  useProviderEffort,
  useProviderMode,
  useProviderModels,
} from "@renderer/state/agent-options";
import type { ConfigOption, SessionMode } from "@shared/acp/types";
import type { AgentStatus } from "@shared/agents";
import type { AgentOptions } from "@shared/ipc/agent-options";

/**
 * What the new-session screen's chips are built from: one model group per
 * **installed** agent that has answered, with the person's stored default
 * already showing, and the one mode chip drawn from whichever shape that
 * agent sends its modes in. The rule this file exists for is the one the
 * user asked for in so many words — an agent nobody can run contributes no
 * models.
 */

const select = (id: string, category: string, values: string[], currentValue: string): ConfigOption => ({
  id,
  name: id,
  description: null,
  category,
  type: "select",
  currentValue,
  options: values.map((value) => ({ value, name: value.toUpperCase(), description: null, group: null, kind: null })),
});

const modes: SessionMode[] = [
  { id: "default", name: "Manual", description: null, kind: "standard" },
  { id: "auto", name: "Auto", description: null, kind: "auto_review" },
  { id: "bypass", name: "Bypass permissions", description: null, kind: "full_access" },
];

const cached = (agentId: string, extra: Partial<AgentOptions> = {}): AgentOptions => ({
  agentId,
  options: [
    select("model", "model", ["fast", "smart"], "fast"),
    select("effort", "thought_level", ["low", "high"], "low"),
  ],
  modes,
  updatedAt: 1,
  defaultModel: null,
  defaultEfforts: {},
  effortOptions: {},
  defaultMode: null,
  ...extra,
});

const agent = (id: string, name: string): AgentStatus =>
  ({ id, name, icon: id, installed: true, launchWithoutBinary: false, auth: "authenticated" }) as AgentStatus;

describe("the agent-options store", () => {
  beforeEach(() => {
    useAgentOptions.setState({ byAgent: {}, ready: false });
  });

  it("gives one model group per installed agent that has answered", () => {
    useAgentOptions.getState().receive([cached("claude-code"), cached("codex")]);
    const agents = [agent("claude-code", "Claude Code"), agent("codex", "Codex")];
    const { result } = renderHook(() => useProviderModels(agents));
    expect(result.current.map((provider) => provider.agentName)).toEqual(["Claude Code", "Codex"]);
    expect(result.current[0]?.model.options.map((option) => option.value)).toEqual(["fast", "smart"]);
  });

  it("leaves out an agent that is not installed, and one whose probe never answered", () => {
    // Only Codex has a snapshot; Claude is installed but has not answered.
    // Gemini answered once but is not installed any more.
    useAgentOptions.getState().receive([cached("codex"), cached("gemini-cli")]);
    const agents = [agent("claude-code", "Claude Code"), agent("codex", "Codex")];
    const { result } = renderHook(() => useProviderModels(agents));
    expect(result.current.map((provider) => provider.agentId)).toEqual(["codex"]);
  });

  it("shows the stored default rather than the snapshot's own current value", () => {
    useAgentOptions.getState().receive([
      cached("codex", { defaultModel: "smart", defaultEfforts: { smart: "high" } }),
    ]);
    const { result } = renderHook(() => useProviderModels([agent("codex", "Codex")]));
    expect(result.current[0]?.model.currentValue).toBe("smart");
    const { result: effort } = renderHook(() => useProviderEffort("codex", "smart"));
    expect(effort.current?.currentValue).toBe("high");
  });

  /**
   * The user's ask: reselecting a model comes back to the level chosen under
   * it. The store keeps one level per model, so the chip is asked which model
   * it is standing next to and answers about that one — a level remembered
   * for the agent would show `smart`'s under `fast` and forget it on the way
   * back.
   */
  it("shows the effort remembered for the model it is asked about", () => {
    useAgentOptions.getState().receive([
      cached("codex", { defaultEfforts: { smart: "high", fast: "low" } }),
    ]);
    const { result: smart } = renderHook(() => useProviderEffort("codex", "smart"));
    expect(smart.current?.currentValue).toBe("high");
    const { result: fast } = renderHook(() => useProviderEffort("codex", "fast"));
    expect(fast.current?.currentValue).toBe("low");
    // A model nobody has picked a level for: the level the agent reports.
    const { result: other } = renderHook(() => useProviderEffort("codex", "opus"));
    expect(other.current?.currentValue).toBe("low");
  });

  /**
   * And the levels themselves are the model's. The snapshot describes
   * whichever model was current when it was taken, so the cache keeps the
   * option seen against each model and the chip draws that model's list.
   */
  it("draws the levels the model it is asked about offers", () => {
    useAgentOptions.getState().receive([
      cached("claude-code", {
        defaultEfforts: { smart: "xhigh" },
        effortOptions: {
          fast: select("effort", "thought_level", ["low", "medium", "high"], "medium"),
          smart: select("effort", "thought_level", ["low", "medium", "high", "xhigh"], "medium"),
        },
      }),
    ]);
    const { result: smart } = renderHook(() => useProviderEffort("claude-code", "smart"));
    expect(smart.current?.options.map((option) => option.value)).toEqual(["low", "medium", "high", "xhigh"]);
    expect(smart.current?.currentValue).toBe("xhigh");
    const { result: fast } = renderHook(() => useProviderEffort("claude-code", "fast"));
    expect(fast.current?.options.map((option) => option.value)).toEqual(["low", "medium", "high"]);
    // `xhigh` is not one of `fast`'s levels, so it is not what the chip shows
    // even if it somehow got stored against it.
    expect(fast.current?.currentValue).toBe("medium");
  });

  it("has no effort chip for an agent whose snapshot has no effort levels", () => {
    useAgentOptions.getState().receive([
      cached("codex", { options: [select("model", "model", ["fast"], "fast")] }),
    ]);
    const { result } = renderHook(() => useProviderEffort("codex", "fast"));
    expect(result.current).toBeNull();
    const { result: unknown } = renderHook(() => useProviderEffort("nobody", null));
    expect(unknown.current).toBeNull();
  });

  /**
   * The mode chip before there is a session: the modes from the snapshot,
   * and the mode the session *will* be created in — the stored default, else
   * the agent's own auto preset, which is what main applies.
   */
  it("shows the mode the next session will start in", () => {
    useAgentOptions.getState().receive([cached("claude-code")]);
    const { result } = renderHook(() => useProviderMode("claude-code"));
    expect(result.current?.source).toBe("modes");
    expect(result.current?.currentModeId).toBe("auto");

    useAgentOptions.getState().receive([cached("claude-code", { defaultMode: "default" })]);
    const { result: stored } = renderHook(() => useProviderMode("claude-code"));
    expect(stored.current?.currentModeId).toBe("default");

    // A default the agent no longer offers is not a mode: back to auto.
    useAgentOptions.getState().receive([cached("claude-code", { defaultMode: "yolo" })]);
    const { result: gone } = renderHook(() => useProviderMode("claude-code"));
    expect(gone.current?.currentModeId).toBe("auto");
  });

  it("falls back to the mode config option for an agent that sends no modes", () => {
    useAgentOptions.getState().receive([
      cached("codex", {
        modes: [],
        options: [
          select("model", "model", ["fast"], "fast"),
          select("mode", "mode", ["read-only", "agent"], "agent"),
        ],
      }),
    ]);
    const { result } = renderHook(() => useProviderMode("codex"));
    expect(result.current?.source).toBe("config_option");
    expect(result.current?.configId).toBe("mode");
    expect(result.current?.modes.map((mode) => mode.id)).toEqual(["read-only", "agent"]);

    // And nothing at all for an agent with neither.
    useAgentOptions.getState().receive([
      cached("gemini-cli", { modes: [], options: [select("model", "model", ["fast"], "fast")] }),
    ]);
    const { result: none } = renderHook(() => useProviderMode("gemini-cli"));
    expect(none.current).toBeNull();
    const { result: unknown } = renderHook(() => useProviderMode("nobody"));
    expect(unknown.current).toBeNull();
  });
});

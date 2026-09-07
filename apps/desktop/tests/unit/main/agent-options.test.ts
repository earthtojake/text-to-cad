import { describe, expect, it, vi } from "vitest";

import { AgentOptionStore, type AgentOptionsDeps } from "@main/acp/agent-options";
import type { ConfigOption } from "@shared/acp/types";
import type { AgentOptions } from "@shared/ipc/agent-options";

/**
 * The per-agent cache the new-session screen's model and effort chips are
 * drawn from: what a live session reported, what a probe took from an agent
 * nobody has run, and the defaults the next session starts at.
 */

const model = (currentValue = "fast"): ConfigOption => ({
  id: "model",
  name: "Model",
  description: null,
  category: "model",
  type: "select",
  currentValue,
  options: [
    { value: "fast", name: "Fast", description: null, group: null, kind: null },
    { value: "smart", name: "Smart", description: null, group: null, kind: null },
  ],
});

const effort = (currentValue = "medium"): ConfigOption => ({
  id: "reasoning_effort",
  name: "Effort",
  description: null,
  category: "thought_level",
  type: "select",
  currentValue,
  options: [
    { value: "low", name: "Low", description: null, group: null, kind: null },
    { value: "medium", name: "Medium", description: null, group: null, kind: null },
    { value: "high", name: "High", description: null, group: null, kind: null },
  ],
});

/** An in-memory stand-in for the sqlite rows, with the same read/write shape. */
function store(overrides: Partial<AgentOptionsDeps> = {}) {
  const rows = new Map<string, AgentOptions>();
  const changes: AgentOptions[][] = [];
  const row = (agentId: string): AgentOptions =>
    rows.get(agentId) ?? {
      agentId,
      options: [],
      updatedAt: null,
      defaultModel: null,
      defaultEffort: null,
    };
  const deps: AgentOptionsDeps = {
    read: () => [...rows.values()],
    get: (agentId) => rows.get(agentId) ?? null,
    writeOptions: (agentId, options) => {
      rows.set(agentId, { ...row(agentId), options, updatedAt: 1 });
    },
    writeDefaults: (agentId, defaults) => {
      const current = row(agentId);
      rows.set(agentId, {
        ...current,
        ...(defaults.model === undefined ? {} : { defaultModel: defaults.model }),
        ...(defaults.effort === undefined ? {} : { defaultEffort: defaults.effort }),
      });
    },
    probe: async () => [],
    onChange: (all) => changes.push(all),
    ...overrides,
  };
  return { deps, rows, changes, subject: new AgentOptionStore(deps) };
}

describe("AgentOptionStore", () => {
  it("keeps what a live session reported, and broadcasts only when it changed", () => {
    const { subject, changes, rows } = store();
    subject.remember("codex", [model(), effort()]);
    expect(rows.get("codex")?.options).toHaveLength(2);
    expect(changes).toHaveLength(1);

    // The same options again — a `config_option_update` that changed nothing
    // else, or a second session with the same agent.
    subject.remember("codex", [model(), effort()]);
    expect(changes).toHaveLength(1);

    subject.remember("codex", [model("smart"), effort()]);
    expect(changes).toHaveLength(2);
  });

  it("ignores an empty snapshot rather than forgetting the one it has", () => {
    const { subject, rows } = store();
    subject.remember("codex", [model()]);
    subject.remember("codex", []);
    expect(rows.get("codex")?.options).toHaveLength(1);
  });

  it("remembers a model or an effort chosen in a session, and nothing else", () => {
    const { subject, rows } = store();
    const options = [model(), effort()];
    subject.rememberChoice("codex", "model", "smart", options);
    subject.rememberChoice("codex", "reasoning_effort", "high", options);
    // A boolean, and an option that is neither: session-scoped, not a default.
    subject.rememberChoice("codex", "web_search", true, options);
    subject.rememberChoice("codex", "collaboration_mode", "plan", options);
    expect(subject.defaults("codex")).toEqual({ model: "smart", effort: "high" });
    expect(rows.get("codex")?.options).toEqual([]);
  });

  it("probes an agent with no snapshot, once, however many callers ask", async () => {
    let resolve: ((options: ConfigOption[]) => void) | null = null;
    const probe = vi.fn(
      () =>
        new Promise<ConfigOption[]>((done) => {
          resolve = done;
        }),
    );
    const { subject, rows } = store({ probe });
    const first = subject.ensure("claude-code", "p1");
    const second = subject.ensure("claude-code", "p1");
    expect(probe).toHaveBeenCalledTimes(1);
    resolve!([model()]);
    await Promise.all([first, second]);
    expect(rows.get("claude-code")?.options).toHaveLength(1);

    // And never again once there is a snapshot.
    await subject.ensure("claude-code", "p1");
    expect(probe).toHaveBeenCalledTimes(1);
  });

  it("does not re-probe an agent that could not answer, until its status changes", async () => {
    const probe = vi.fn(async () => {
      throw new Error("not signed in");
    });
    const failures: string[] = [];
    const { subject, rows } = store({ probe, onProbeFailed: (agentId) => failures.push(agentId) });
    await subject.ensure("codex", null);
    await subject.ensure("codex", null);
    expect(probe).toHaveBeenCalledTimes(1);
    expect(failures).toEqual(["codex"]);
    // Silence: an agent that cannot be probed contributes no models, which is
    // what the new-session screen shows for it.
    expect(rows.get("codex")).toBeUndefined();

    subject.forgetFailures();
    await subject.ensure("codex", null);
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("treats an agent that answers with no options as one that did not answer", async () => {
    const probe = vi.fn(async () => []);
    const { subject, rows } = store({ probe });
    await subject.ensure("codex", null);
    expect(rows.get("codex")).toBeUndefined();
    await subject.ensure("codex", null);
    expect(probe).toHaveBeenCalledTimes(1);
  });

  it("sets one default without clearing the other", () => {
    const { subject } = store();
    subject.setDefaults("codex", { model: "smart" });
    subject.setDefaults("codex", { effort: "high" });
    expect(subject.defaults("codex")).toEqual({ model: "smart", effort: "high" });
    subject.setDefaults("codex", { model: null });
    expect(subject.defaults("codex")).toEqual({ model: null, effort: "high" });
  });
});

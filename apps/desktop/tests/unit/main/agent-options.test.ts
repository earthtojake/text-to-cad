import { describe, expect, it, vi } from "vitest";

import { AgentOptionStore, type AgentOptionsDeps, type AgentSnapshot } from "@main/acp/agent-options";
import { effortModelKey, effortOption } from "@shared/acp/options";
import type { ConfigOption, SessionMode } from "@shared/acp/types";
import type { AgentOptions } from "@shared/ipc/agent-options";

/**
 * The per-agent cache the new-session screen's model, effort and mode chips
 * are drawn from: what a live session reported, what a probe took from an
 * agent nobody has run, and the defaults the next session starts at.
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

/**
 * The effort option, with the levels of one model. `levels` is a parameter
 * because the list is per model — the point of migration 9 — and `xhigh`
 * exists for the bigger of the two the way it does on Claude.
 */
const effort = (currentValue = "medium", levels = ["low", "medium", "high"]): ConfigOption => ({
  id: "reasoning_effort",
  name: "Effort",
  description: null,
  category: "thought_level",
  type: "select",
  currentValue,
  options: levels.map((value) => ({
    value,
    name: value,
    description: null,
    group: null,
    kind: null,
  })),
});

const modes: SessionMode[] = [
  { id: "default", name: "Manual", description: null, kind: "standard" },
  { id: "auto", name: "Auto", description: null, kind: "auto_review" },
];

/** Codex's shape: the same list as a `mode`-category config option. */
const modeOption = (currentValue = "auto"): ConfigOption => ({
  id: "mode",
  name: "Mode",
  description: null,
  category: "mode",
  type: "select",
  currentValue,
  options: modes.map((mode) => ({
    value: mode.id,
    name: mode.name,
    description: null,
    group: null,
    kind: mode.kind,
  })),
});

const snapshot = (
  configOptions: ConfigOption[] = [],
  sessionModes: SessionMode[] = [],
): AgentSnapshot => ({ configOptions, modes: sessionModes });

/**
 * An in-memory stand-in for the sqlite rows, with the same read/write shape —
 * including the two maps migration 9 made of the effort: the level picked per
 * model, and the levels each model offers (filed by `writeOptions` under
 * whichever model the snapshot was taken with, exactly as the repository
 * does).
 */
function store(overrides: Partial<AgentOptionsDeps> = {}) {
  const rows = new Map<string, AgentOptions>();
  const changes: AgentOptions[][] = [];
  const row = (agentId: string): AgentOptions =>
    rows.get(agentId) ?? {
      agentId,
      options: [],
      modes: [],
      updatedAt: null,
      defaultModel: null,
      defaultEfforts: {},
      effortOptions: {},
      defaultMode: null,
    };
  const deps: AgentOptionsDeps = {
    read: () => [...rows.values()],
    get: (agentId) => rows.get(agentId) ?? null,
    writeOptions: (agentId, options, agentModes) => {
      const current = row(agentId);
      const levels = effortOption(options);
      rows.set(agentId, {
        ...current,
        options,
        modes: agentModes,
        updatedAt: 1,
        effortOptions: levels
          ? { ...current.effortOptions, [effortModelKey(options)]: levels }
          : current.effortOptions,
      });
    },
    writeDefaults: (agentId, defaults) => {
      const current = row(agentId);
      rows.set(agentId, {
        ...current,
        ...(defaults.model === undefined ? {} : { defaultModel: defaults.model }),
        ...(defaults.mode === undefined ? {} : { defaultMode: defaults.mode }),
      });
    },
    writeEffort: (agentId, model, value) => {
      const current = row(agentId);
      const efforts = { ...current.defaultEfforts };
      if (value === null) {
        delete efforts[model];
      } else {
        efforts[model] = value;
      }
      rows.set(agentId, { ...current, defaultEfforts: efforts });
    },
    probe: async () => snapshot(),
    onChange: (all) => changes.push(all),
    ...overrides,
  };
  return { deps, rows, changes, subject: new AgentOptionStore(deps) };
}

describe("AgentOptionStore", () => {
  it("keeps what a live session reported, and broadcasts only when it changed", () => {
    const { subject, changes, rows } = store();
    subject.remember("codex", [model(), effort()], modes);
    expect(rows.get("codex")?.options).toHaveLength(2);
    expect(rows.get("codex")?.modes).toEqual(modes);
    expect(changes).toHaveLength(1);

    // The same options again — a `config_option_update` that changed nothing
    // else, or a second session with the same agent.
    subject.remember("codex", [model(), effort()], modes);
    expect(changes).toHaveLength(1);

    subject.remember("codex", [model("smart"), effort()], modes);
    expect(changes).toHaveLength(2);

    // The modes alone changing is a change too: they are half of what the
    // new-session screen draws.
    subject.remember("codex", [model("smart"), effort()], [modes[0]!]);
    expect(changes).toHaveLength(3);
  });

  it("ignores an empty snapshot rather than forgetting the one it has", () => {
    const { subject, rows } = store();
    subject.remember("codex", [model()], modes);
    subject.remember("codex", [], []);
    expect(rows.get("codex")?.options).toHaveLength(1);
    expect(rows.get("codex")?.modes).toEqual(modes);
  });

  it("remembers a model, an effort or a mode chosen in a session, and nothing else", () => {
    const { subject, rows } = store();
    const options = [model(), effort(), modeOption()];
    subject.rememberChoice("codex", "model", "smart", options);
    subject.rememberChoice("codex", "reasoning_effort", "high", options);
    // The `mode` option is the mode chip for an agent that sends its modes
    // that way, so the mode it was switched to is the next session's too.
    subject.rememberChoice("codex", "mode", "default", options);
    // A boolean, and an option that is none of the three: session-scoped.
    subject.rememberChoice("codex", "web_search", true, options);
    subject.rememberChoice("codex", "collaboration_mode", "plan", options);
    expect(subject.defaults("codex")).toEqual({ model: "smart", mode: "default" });
    // The effort is filed against the model the options were on when it was
    // picked — `fast` — not against the model that was switched to.
    expect(rows.get("codex")?.defaultEfforts).toEqual({ fast: "high" });
    expect(subject.effortFor("codex", "fast")).toBe("high");
    expect(subject.effortFor("codex", "smart")).toBeNull();
    expect(rows.get("codex")?.options).toEqual([]);
  });

  /**
   * The user's ask, in the smallest form it fits: pick a level under one
   * model, pick another under the second, and each model keeps its own. One
   * `default_effort` per agent could not — the second pick overwrote the
   * first, and coming back to the first model showed the second's level.
   */
  it("keeps one effort per model, and a model pick leaves them all alone", () => {
    const { subject } = store();
    subject.rememberChoice("claude-code", "reasoning_effort", "xhigh", [
      model("smart"),
      effort("medium", ["low", "medium", "high", "xhigh"]),
    ]);
    subject.rememberChoice("claude-code", "reasoning_effort", "low", [model("fast"), effort()]);
    expect(subject.effortFor("claude-code", "smart")).toBe("xhigh");
    expect(subject.effortFor("claude-code", "fast")).toBe("low");

    // Switching model — either way round — says nothing about any effort.
    subject.rememberChoice("claude-code", "model", "smart", [model("fast"), effort()]);
    subject.rememberChoice("claude-code", "model", "fast", [model("smart"), effort()]);
    expect(subject.effortFor("claude-code", "smart")).toBe("xhigh");
    expect(subject.effortFor("claude-code", "fast")).toBe("low");
    expect(subject.defaults("claude-code").model).toBe("fast");
  });

  /**
   * An agent with an effort option but no model dropdown: there is one level
   * to remember and no model to hang it on, so it goes under `NO_MODEL` and
   * is found again by an `effortFor` asked with no model.
   */
  it("remembers the effort of an agent that offers no models", () => {
    const { subject, rows } = store();
    subject.rememberChoice("gemini-cli", "reasoning_effort", "high", [effort()]);
    expect(rows.get("gemini-cli")?.defaultEfforts).toEqual({ "": "high" });
    expect(subject.effortFor("gemini-cli", null)).toBe("high");
  });

  /**
   * The levels themselves, per model. A snapshot only ever describes the
   * model it was taken with — Claude reports `effort` for the current model
   * — so the cache has to accumulate them, or picking a model on the
   * new-session screen would offer the previous model's list.
   */
  it("keeps each model's effort levels as sessions report them", () => {
    const { subject, rows } = store();
    subject.remember("claude-code", [model("fast"), effort()], modes);
    expect(Object.keys(rows.get("claude-code")!.effortOptions)).toEqual(["fast"]);

    subject.remember(
      "claude-code",
      [model("smart"), effort("medium", ["low", "medium", "high", "xhigh"])],
      modes,
    );
    const levels = rows.get("claude-code")!.effortOptions;
    expect(Object.keys(levels).sort()).toEqual(["fast", "smart"]);
    const smart = levels.smart;
    expect(smart?.type === "select" ? smart.options.map((option) => option.value) : []).toContain("xhigh");
    const fast = levels.fast;
    expect(fast?.type === "select" ? fast.options.map((option) => option.value) : []).not.toContain("xhigh");
  });

  it("remembers the mode a live session was switched into", () => {
    const { subject } = store();
    subject.rememberMode("claude-code", "plan");
    expect(subject.defaults("claude-code").mode).toBe("plan");
  });

  it("probes an agent with no snapshot, once, however many callers ask", async () => {
    let resolve: ((snapshot: AgentSnapshot) => void) | null = null;
    const probe = vi.fn(
      () =>
        new Promise<AgentSnapshot>((done) => {
          resolve = done;
        }),
    );
    const { subject, rows } = store({ probe });
    const first = subject.ensure("claude-code", "p1");
    const second = subject.ensure("claude-code", "p1");
    expect(probe).toHaveBeenCalledTimes(1);
    resolve!(snapshot([model()], modes));
    await Promise.all([first, second]);
    expect(rows.get("claude-code")?.options).toHaveLength(1);
    // Claude's modes come in the same `session/new` reply as its options, and
    // the probe is the only place a screen with no session can get them.
    expect(rows.get("claude-code")?.modes).toEqual(modes);

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

  it("treats an agent that answers with nothing as one that did not answer", async () => {
    const probe = vi.fn(async () => snapshot());
    const { subject, rows } = store({ probe });
    await subject.ensure("codex", null);
    expect(rows.get("codex")).toBeUndefined();
    await subject.ensure("codex", null);
    expect(probe).toHaveBeenCalledTimes(1);
  });

  it("sets one default without clearing the others", () => {
    const { subject } = store();
    subject.setDefaults("codex", { model: "smart" });
    subject.setEffort("codex", "smart", "high");
    subject.setDefaults("codex", { mode: "plan" });
    expect(subject.defaults("codex")).toEqual({ model: "smart", mode: "plan" });
    expect(subject.effortFor("codex", "smart")).toBe("high");
    subject.setDefaults("codex", { model: null });
    expect(subject.defaults("codex")).toEqual({ model: null, mode: "plan" });
    expect(subject.effortFor("codex", "smart")).toBe("high");
    // And forgetting one leaves the others: the chip goes back to the level
    // the agent reports for that model.
    subject.setEffort("codex", "fast", "low");
    subject.setEffort("codex", "smart", null);
    expect(subject.effortFor("codex", "smart")).toBeNull();
    expect(subject.effortFor("codex", "fast")).toBe("low");
  });
});

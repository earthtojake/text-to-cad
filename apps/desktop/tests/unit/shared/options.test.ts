import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { configOptions, sessionModes } from "@shared/acp/reduce";
import {
  NO_MODEL,
  autoModeId,
  effortModelKey,
  effortOption,
  effortOptionFor,
  fastOption,
  isEffortOption,
  isFullAccessMode,
  modeChoice,
  modeOption,
  modelOption,
  preferredEffort,
  preferredMode,
  withCurrentValue,
} from "@shared/acp/options";

/**
 * Which option is the model, which is the effort, and where the one mode
 * chip's modes come from — checked against the **recorded** replies of both
 * adapters, because the whole point of these predicates is that neither
 * adapter agrees with the other about ids.
 */
const fixtures = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures", "acp");

function codexNewSession(): { modes: unknown; configOptions: unknown } {
  const lines = readFileSync(path.join(fixtures, "codex-session.jsonl"), "utf8").split("\n").filter(Boolean);
  for (const line of lines) {
    const frame = JSON.parse(line) as { msg: { result?: { sessionId?: string } } };
    const result = frame.msg.result;
    if (result?.sessionId) {
      return result as { modes: unknown; configOptions: unknown };
    }
  }
  throw new Error("no session/new reply in the codex fixture");
}

/** Claude's reply, as `scripts/acp-harness.mjs` records it (README, ACP). */
const CLAUDE_MODES = [
  { id: "default", name: "Manual", _meta: { kind: "standard" } },
  { id: "acceptEdits", name: "Accept edits", _meta: { kind: "standard" } },
  { id: "plan", name: "Plan", _meta: { kind: "plan" } },
  { id: "auto", name: "Auto", _meta: { kind: "auto_review" } },
  { id: "bypassPermissions", name: "Bypass permissions", _meta: { kind: "full_access" } },
];

const CLAUDE_CONFIG = [
  { id: "mode", name: "Mode", category: "mode", type: "select", currentValue: "default", options: CLAUDE_MODES.map((mode) => ({ value: mode.id, name: mode.name, _meta: mode._meta })) },
  { id: "model", name: "Model", category: "model", type: "select", currentValue: "sonnet", options: [{ value: "sonnet", name: "Sonnet" }, { value: "haiku", name: "Haiku" }] },
  { id: "effort", name: "Effort", category: "thought_level", type: "select", currentValue: "high", options: [{ value: "low", name: "Low" }, { value: "high", name: "High" }] },
  { id: "agent", name: "Agent", category: null, type: "select", currentValue: "default", options: [{ value: "default", name: "Default" }] },
  { id: "fast", name: "Fast", category: "model_config", type: "boolean", currentValue: false },
];

describe("which option is which", () => {
  it("finds Claude's model, effort and mode, and leaves its agent persona alone", () => {
    const options = configOptions(CLAUDE_CONFIG);
    expect(modelOption(options)?.id).toBe("model");
    expect(effortOption(options)?.id).toBe("effort");
    expect(modeOption(options)?.id).toBe("mode");
    // The persona option is what used to fill the options chip with somebody
    // else's plugin agents. Nothing claims it now.
    expect(options.find((option) => option.id === "agent")).toBeDefined();
    expect(isEffortOption({ id: "agent", category: null })).toBe(false);
  });

  it("finds Codex's, whose ids are different in every case", () => {
    const options = configOptions(codexNewSession().configOptions);
    expect(modelOption(options)?.id).toBe("model");
    expect(effortOption(options)?.id).toBe("reasoning_effort");
    expect(modeOption(options)?.id).toBe("mode");
    expect(fastOption(options)).toMatchObject({ id: "fast-mode", on: false, value: "on" });
  });

  it("reads the fast switch as either type an adapter sends it", () => {
    expect(fastOption(configOptions(CLAUDE_CONFIG))).toMatchObject({ id: "fast", on: false, value: true });
    const on = configOptions([{ id: "fast", name: "Fast", type: "boolean", currentValue: true }]);
    expect(fastOption(on)).toMatchObject({ on: true, value: false });
  });

  it("is unmoved by an option that only sounds like an effort", () => {
    expect(isEffortOption({ id: "reasoning_effort", category: null })).toBe(true);
    expect(isEffortOption({ id: "effortless", category: null })).toBe(false);
    expect(isEffortOption({ id: "whatever", category: "thought_level" })).toBe(true);
  });
});

describe("the agent's own auto mode", () => {
  it("is Claude's `auto` and Codex's `agent`, by _meta.kind rather than by id", () => {
    expect(autoModeId(sessionModes(CLAUDE_MODES))).toBe("auto");
    const codex = codexNewSession().modes as { availableModes: unknown };
    expect(autoModeId(sessionModes(codex.availableModes))).toBe("agent");
  });

  it("falls back to a mode plainly called auto, and is null when there is none", () => {
    expect(autoModeId(sessionModes([{ id: "auto", name: "Automatic" }]))).toBe("auto");
    expect(autoModeId(sessionModes([{ id: "default", name: "Default" }]))).toBeNull();
  });
});

/**
 * The one chip's source. Both adapters answer with `modes` *and* a `mode`
 * config option; `modes` is the protocol's own field and the one their
 * `current_mode_update` reports against, so it wins — and an agent that
 * sends only the option is read through the same shape, so the chip, the
 * create-time default and these tests speak one language.
 */
describe("where the mode chip's modes come from", () => {
  it("prefers the session's modes over the mode config option", () => {
    const choice = modeChoice({
      modes: sessionModes(CLAUDE_MODES),
      configOptions: configOptions(CLAUDE_CONFIG),
      currentModeId: "plan",
    })!;
    expect(choice.source).toBe("modes");
    expect(choice.configId).toBeNull();
    expect(choice.currentModeId).toBe("plan");
    expect(choice.modes.map((mode) => mode.id)).toEqual(CLAUDE_MODES.map((mode) => mode.id));
    expect(autoModeId(choice.modes)).toBe("auto");
  });

  it("reads a mode-category select as modes for an agent that sends no modes", () => {
    const choice = modeChoice({
      modes: [],
      configOptions: configOptions(codexNewSession().configOptions),
      currentModeId: null,
    })!;
    expect(choice.source).toBe("config_option");
    expect(choice.configId).toBe("mode");
    // Its current value is the mode the session is in, and the values are
    // modes: `_meta.kind` and all, so the auto preset is still findable.
    expect(choice.currentModeId).toBe("agent");
    expect(choice.modes.map((mode) => mode.id)).toEqual(["read-only", "agent", "agent-full-access"]);
    expect(autoModeId(choice.modes)).toBe("agent");
  });

  it("is nothing when there is nothing to choose between", () => {
    expect(modeChoice({ modes: [], configOptions: [], currentModeId: null })).toBeNull();
    // One mode is not a decision, and neither is a one-value select.
    expect(
      modeChoice({
        modes: sessionModes([{ id: "default", name: "Default" }]),
        configOptions: [],
        currentModeId: "default",
      }),
    ).toBeNull();
    expect(
      modeChoice({
        modes: [],
        configOptions: configOptions([
          { id: "mode", name: "Mode", category: "mode", type: "select", currentValue: "a", options: [{ value: "a", name: "A" }] },
        ]),
        currentModeId: null,
      }),
    ).toBeNull();
  });

  it("names the one mode that asks about nothing, in either provider's words", () => {
    const claude = sessionModes(CLAUDE_MODES);
    expect(claude.filter(isFullAccessMode).map((mode) => mode.id)).toEqual(["bypassPermissions"]);
    const codex = modeChoice({
      modes: [],
      configOptions: configOptions(codexNewSession().configOptions),
      currentModeId: null,
    })!;
    expect(codex.modes.filter(isFullAccessMode).map((mode) => mode.id)).toEqual(["agent-full-access"]);
    // An adapter that sends no `_meta.kind` is caught by the name it shows.
    expect(isFullAccessMode({ id: "x", name: "Full access", description: null, kind: null })).toBe(true);
    expect(isFullAccessMode({ id: "y", name: "Accept edits", description: null, kind: null })).toBe(false);
  });
});

describe("withCurrentValue", () => {
  it("applies a stored default the agent still offers, and ignores one it does not", () => {
    const model = modelOption(configOptions(CLAUDE_CONFIG))!;
    expect(withCurrentValue(model, "haiku").currentValue).toBe("haiku");
    expect(withCurrentValue(model, "opus-3").currentValue).toBe("sonnet");
    expect(withCurrentValue(model, null)).toBe(model);
  });
});

/**
 * What is remembered at which grain, resolved: the **model** per provider,
 * the **effort** per provider and model, the **mode** per provider. These are
 * the three answers the new-session screen's chips draw and the three
 * `SessionManager.create` applies, so they are one file's decision.
 *
 * The effort is the one that needs the model. Claude reports its `effort`
 * option for whichever model the session is on, with the levels that model
 * has: `sonnet` is asked at `high`, and a bigger model would offer a level
 * `sonnet` does not. One level per agent therefore names no model — which is
 * how switching model carried the old level across and switching back forgot
 * the earlier pick.
 */
describe("the remembered model, effort and mode", () => {
  /** Claude's shape with a second model whose levels go one further. */
  const SMART_EFFORT = {
    id: "effort",
    name: "Effort",
    category: "thought_level",
    type: "select",
    currentValue: "medium",
    options: [{ value: "low", name: "Low" }, { value: "medium", name: "Medium" }, { value: "high", name: "High" }, { value: "xhigh", name: "Xhigh" }],
  };

  it("keys an effort by the model the options were on", () => {
    expect(effortModelKey(configOptions(CLAUDE_CONFIG))).toBe("sonnet");
    // An agent with an effort but no model dropdown: one level, no model to
    // hang it on.
    expect(effortModelKey(configOptions([CLAUDE_CONFIG[2]!]))).toBe(NO_MODEL);
    expect(effortModelKey([])).toBe(NO_MODEL);
  });

  it("draws each model's own levels, and falls back to the snapshot's for one nobody has run", () => {
    const options = configOptions(CLAUDE_CONFIG);
    const perModel = { opus: configOptions([SMART_EFFORT])[0]! };
    expect(effortOptionFor(options, perModel, "opus")?.options.map((option) => option.value)).toEqual([
      "low",
      "medium",
      "high",
      "xhigh",
    ]);
    // `sonnet` has none cached: the snapshot's own, which was taken with it.
    expect(effortOptionFor(options, perModel, "sonnet")?.options.map((option) => option.value)).toEqual([
      "low",
      "high",
    ]);
    expect(effortOptionFor(options, {}, null)?.id).toBe("effort");
    // No effort option at all is no chip.
    expect(effortOptionFor(configOptions([CLAUDE_CONFIG[1]!]), {}, "sonnet")).toBeNull();
  });

  it("sits at the level remembered for that model, else the one the agent reports", () => {
    const sonnet = effortOption(configOptions(CLAUDE_CONFIG))!;
    const opus = effortOption(configOptions([SMART_EFFORT]))!;
    const efforts = { sonnet: "low", opus: "xhigh" };
    expect(preferredEffort(sonnet, efforts, "sonnet")).toBe("low");
    expect(preferredEffort(opus, efforts, "opus")).toBe("xhigh");
    // Nothing remembered for this model: the agent's own current for it.
    expect(preferredEffort(sonnet, efforts, "haiku")).toBe("high");
    expect(preferredEffort(sonnet, {}, "sonnet")).toBe("high");
    // A level that model does not have — `xhigh` under `sonnet` — is not an
    // answer, so the agent's own stands.
    expect(preferredEffort(sonnet, { sonnet: "xhigh" }, "sonnet")).toBe("high");
    // An agent with no model dropdown remembers its one level under NO_MODEL.
    expect(preferredEffort(sonnet, { [NO_MODEL]: "low" }, null)).toBe("low");
    expect(preferredEffort(null, efforts, "sonnet")).toBeNull();
  });

  it("starts in the mode the provider was left in, else its own auto preset", () => {
    const modes = sessionModes(CLAUDE_MODES);
    expect(preferredMode(modes, "plan")).toBe("plan");
    // A mode the agent dropped is not a mode.
    expect(preferredMode(modes, "yolo")).toBe("auto");
    expect(preferredMode(modes, null)).toBe("auto");
    // And an agent with no auto preset is left alone rather than guessed at.
    expect(preferredMode(sessionModes([{ id: "a", name: "A" }, { id: "b", name: "B" }]), null)).toBeNull();
  });
});

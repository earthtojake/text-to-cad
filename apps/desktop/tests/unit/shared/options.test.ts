import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { configOptions, sessionModes } from "@shared/acp/reduce";
import {
  autoModeId,
  defaultModeId,
  effortOption,
  fastOption,
  isEffortOption,
  isFullAccessMode,
  modeChoice,
  modeOption,
  modelOption,
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

  it("starts Claude Code and Codex in their own auto presets by name, and falls back to the kind", () => {
    const codex = codexNewSession().modes as { availableModes: unknown };
    expect(defaultModeId("claude-code", sessionModes(CLAUDE_MODES))).toBe("auto");
    expect(defaultModeId("codex", sessionModes(codex.availableModes))).toBe("agent");
    // An override the agent does not offer is not forced on it.
    expect(defaultModeId("codex", sessionModes([{ id: "default", name: "Default" }, { id: "auto", name: "Auto" }]))).toBe("auto");
    // Providers without an override use the auto-review rule.
    expect(defaultModeId("gemini-cli", sessionModes(codex.availableModes))).toBe("agent");
    expect(defaultModeId(null, sessionModes([{ id: "default", name: "Default" }]))).toBeNull();
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

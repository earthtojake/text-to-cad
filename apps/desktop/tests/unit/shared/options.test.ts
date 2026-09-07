import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { configOptions, sessionModes } from "@shared/acp/reduce";
import {
  autoModeId,
  autoModeValue,
  effortOption,
  fastOption,
  isEffortOption,
  modeOption,
  modelOption,
  withCurrentValue,
} from "@shared/acp/options";

/**
 * Which option is the model, which is the effort, and which mode is the
 * agent's own auto-approval preset — checked against the **recorded** replies
 * of both adapters, because the whole point of these predicates is that
 * neither adapter agrees with the other about ids.
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

  it("is the same preset among the mode option's values", () => {
    expect(autoModeValue(modeOption(configOptions(CLAUDE_CONFIG)))).toBe("auto");
    expect(autoModeValue(modeOption(configOptions(codexNewSession().configOptions)))).toBe("agent");
  });

  it("falls back to a mode plainly called auto, and is null when there is none", () => {
    expect(autoModeId(sessionModes([{ id: "auto", name: "Automatic" }]))).toBe("auto");
    expect(autoModeId(sessionModes([{ id: "default", name: "Default" }]))).toBeNull();
    expect(autoModeValue(null)).toBeNull();
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

/**
 * Which of an agent's config options is the model, which is the effort, and
 * where its modes come from.
 *
 * Every agent invents its own ids — Claude's `model` / `effort` / `auto`,
 * Codex's `model` / `reasoning_effort` / `agent` — so the app matches on the
 * ACP `category` and on `_meta.kind` first, and falls back to the handful of
 * ids the two adapters actually ship. Shared: main applies these when a
 * session is created (`src/main/acp/sessions.ts`), the renderer draws the
 * chips from the same answers, and the tests check both against one file.
 *
 * The mode is the app's **only** permission control (README, "Permissions"):
 * there is no second, app-side approval setting over the top of it, so
 * whichever of the two shapes an agent sends its modes in has to reach one
 * chip. `modeChoice` is that answer.
 *
 * No Node, no React, no zod: pure predicates over the parsed state.
 */
import type { ConfigOption, SessionMode } from "./types";

export type SelectOption = Extract<ConfigOption, { type: "select" }>;
export type BooleanOption = Extract<ConfigOption, { type: "boolean" }>;

/** ACP's `_meta.kind` for a provider's own auto-approval preset. */
export const AUTO_REVIEW_KIND = "auto_review";
/** ACP's `_meta.kind` for the mode that asks about nothing at all. */
export const FULL_ACCESS_KIND = "full_access";

const EFFORT_IDS = ["reasoning_effort", "effort", "thinking_level", "thought_level"];
/** The one-switch speed option: Claude's `fast`, Codex's `fast-mode`. */
const FAST_IDS = ["fast", "fast-mode", "fast_mode"];

export function selectOptions(options: ConfigOption[]): SelectOption[] {
  return options.filter((option): option is SelectOption => option.type === "select");
}

export function isEffortOption(option: { id: string; category: string | null }): boolean {
  return option.category === "thought_level" || EFFORT_IDS.includes(option.id);
}

export function isFastOption(option: { id: string; name: string }): boolean {
  return FAST_IDS.includes(option.id) || /^fast( mode)?$/i.test(option.name);
}

/** The model dropdown, or null for an agent that does not offer one. */
export function modelOption(options: ConfigOption[]): SelectOption | null {
  return selectOptions(options).find((option) => option.category === "model") ?? null;
}

/** The effort dropdown. Claude only sends one when the chosen model supports it. */
export function effortOption(options: ConfigOption[]): SelectOption | null {
  return selectOptions(options).find(isEffortOption) ?? null;
}

/**
 * The mode as a config option — both adapters ship one. Read through
 * `modeChoice` rather than directly: which of the two shapes an agent's
 * modes come in is that function's decision, and one caller reading this
 * alone is how the chip ends up disagreeing with the setter.
 */
export function modeOption(options: ConfigOption[]): SelectOption | null {
  return selectOptions(options).find((option) => option.category === "mode") ?? null;
}

/**
 * The `fast` switch, as either type the adapters send it: a boolean option,
 * or a two-value on/off select. Returned as one shape so the model menu's
 * last row does not have to care.
 */
export function fastOption(
  options: ConfigOption[],
): { id: string; name: string; on: boolean; value: string | boolean } | null {
  for (const option of options) {
    if (!isFastOption(option)) {
      continue;
    }
    if (option.type === "boolean") {
      return { id: option.id, name: option.name, on: option.currentValue, value: !option.currentValue };
    }
    const on = /^(on|true|enabled)$/i.test(option.currentValue);
    const next = option.options.find((candidate) =>
      on ? /^(off|false|disabled)$/i.test(candidate.value) : /^(on|true|enabled)$/i.test(candidate.value),
    );
    if (next) {
      return { id: option.id, name: option.name, on, value: next.value };
    }
  }
  return null;
}

/**
 * The provider's own auto-approval mode — Claude's `Auto`, Codex's `Approve
 * for me` — by `_meta.kind` and, for an adapter that sends none, by name.
 * Null when the agent has no such preset, which is the case worth leaving
 * alone rather than guessing at.
 */
/**
 * The mode a provider starts in unless the person has chosen one. Claude Code
 * and Codex both open in their own auto-approval preset in their own apps,
 * so Hardcore does the same by name; any other provider gets the
 * `auto_review` rule below, and an override that names a mode the agent did
 * not offer falls through to it.
 */
export const PROVIDER_DEFAULT_MODES: Readonly<Record<string, string>> = {
  "claude-code": "auto",
  codex: "agent",
};

export function defaultModeId(agentId: string | null | undefined, modes: SessionMode[]): string | null {
  const override = agentId ? PROVIDER_DEFAULT_MODES[agentId] : undefined;
  if (override && modes.some((mode) => mode.id === override)) {
    return override;
  }
  return autoModeId(modes);
}

export function autoModeId(modes: SessionMode[]): string | null {
  const byKind = modes.find((mode) => mode.kind === AUTO_REVIEW_KIND);
  if (byKind) {
    return byKind.id;
  }
  return modes.find((mode) => /^auto$/i.test(mode.id) || /^auto$/i.test(mode.name))?.id ?? null;
}

/**
 * Where one agent's modes live, as one shape.
 *
 * ACP grew two ways of saying the same thing and the adapters use both:
 * Claude and Codex each answer `session/new` with `modes` — switched by
 * `session/set_mode` — *and* with a `mode`-category select config option,
 * switched by `session/set_config_option`. `modes` wins where both are
 * there: it is the protocol's own field, and the one every adapter's
 * `current_mode_update` reports against. An agent with a single mode has no
 * decision to offer and gets no chip.
 *
 * `modes` is the vocabulary either way — a config option's values are read
 * as modes — so the chip, the create-time default and the tests speak one
 * language and only the setter differs.
 */
export type ModeChoice = {
  /** Which call changes it: `session/set_mode`, or `session/set_config_option`. */
  source: "modes" | "config_option";
  /** The option's id when `source` is `config_option`; null for `modes`. */
  configId: string | null;
  modes: SessionMode[];
  currentModeId: string | null;
};

export function modeChoice(input: {
  modes: SessionMode[];
  configOptions: ConfigOption[];
  currentModeId: string | null;
}): ModeChoice | null {
  if (input.modes.length > 1) {
    return { source: "modes", configId: null, modes: input.modes, currentModeId: input.currentModeId };
  }
  const option = modeOption(input.configOptions);
  if (option && option.options.length > 1) {
    return {
      source: "config_option",
      configId: option.id,
      modes: option.options.map((candidate) => ({
        id: candidate.value,
        name: candidate.name,
        description: candidate.description,
        kind: candidate.kind,
      })),
      currentModeId: option.currentValue,
    };
  }
  return null;
}

/**
 * The mode that asks about nothing — Claude's `Bypass permissions`, Codex's
 * `Full access`. The one mode the menu says something extra about, because
 * it is the one choice that removes every checkpoint.
 */
export function isFullAccessMode(mode: SessionMode): boolean {
  return mode.kind === FULL_ACCESS_KIND || /^(full access|bypass permissions)$/i.test(mode.name);
}

/** The name an option's current value goes by, for a chip's label. */
export function currentName(option: SelectOption): string {
  return option.options.find((candidate) => candidate.value === option.currentValue)?.name ?? option.currentValue;
}

/**
 * The same option with a different current value, for the new-session chips:
 * they draw a cached snapshot of an agent that is not running, with the
 * person's stored default (or their pick in this screen) on top of it.
 */
export function withCurrentValue(option: SelectOption, value: string | null | undefined): SelectOption {
  if (!value || value === option.currentValue || !option.options.some((candidate) => candidate.value === value)) {
    return option;
  }
  return { ...option, currentValue: value };
}

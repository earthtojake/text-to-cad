/**
 * Which of an agent's config options is the model, which is the effort, and
 * which of its modes is its own auto-approval preset.
 *
 * Every agent invents its own ids — Claude's `model` / `effort` / `auto`,
 * Codex's `model` / `reasoning_effort` / `agent` — so the app matches on the
 * ACP `category` and on `_meta.kind` first, and falls back to the handful of
 * ids the two adapters actually ship. Shared: main applies these when a
 * session is created (`src/main/acp/sessions.ts`), the renderer draws the
 * chips from the same answers, and the tests check both against one file.
 *
 * No Node, no React, no zod: pure predicates over the parsed state.
 */
import type { ConfigOption, SessionMode } from "./types";

export type SelectOption = Extract<ConfigOption, { type: "select" }>;
export type BooleanOption = Extract<ConfigOption, { type: "boolean" }>;

/** ACP's `_meta.kind` for a provider's own auto-approval preset. */
export const AUTO_REVIEW_KIND = "auto_review";

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

/** The agent's approval preset as a config option (Codex; Claude has one too). */
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
export function autoModeId(modes: SessionMode[]): string | null {
  const byKind = modes.find((mode) => mode.kind === AUTO_REVIEW_KIND);
  if (byKind) {
    return byKind.id;
  }
  return modes.find((mode) => /^auto$/i.test(mode.id) || /^auto$/i.test(mode.name))?.id ?? null;
}

/** The same preset as a value of the `mode` config option, for an agent that has no modes. */
export function autoModeValue(option: SelectOption | null): string | null {
  if (!option) {
    return null;
  }
  const byKind = option.options.find((candidate) => candidate.kind === AUTO_REVIEW_KIND);
  if (byKind) {
    return byKind.value;
  }
  return (
    option.options.find((candidate) => /^auto$/i.test(candidate.value) || /^auto$/i.test(candidate.name))
      ?.value ?? null
  );
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

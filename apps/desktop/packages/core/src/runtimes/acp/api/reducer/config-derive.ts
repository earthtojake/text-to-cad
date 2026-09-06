/**
 * Pure derivation of SessionConfigState groups from a raw ACP SessionConfigOption array.
 *
 * The ACP SDK passes config options as a flat array, each tagged with a `category`
 * string and a `type`. This module maps the known categories to first-class typed
 * groups in SessionConfigState. Unknown categories (e.g. Claude's `model_config`
 * fast-mode toggle) are silently ignored — they remain extension points.
 *
 * Stateless and side-effect-free; safe to call on every config_option_update.
 */

import type { SessionConfigOption } from '@agentclientprotocol/sdk';
import type { EffortOption, ModeOption, ModelChoice, SessionConfigState } from '../models/config';

/** Shape of a single ACP option entry within a select-type config option. */
type RawOption = { value: string; name: string; description?: string | null };
type RawOptionGroup = { options: RawOption[] };

function toEffortOption(raw: RawOption): EffortOption {
  const opt: EffortOption = { id: raw.value, name: raw.name };
  if (raw.description) opt.description = raw.description;
  return opt;
}

function toModeOption(raw: RawOption): ModeOption {
  const opt: ModeOption = { id: raw.value, name: raw.name };
  if (raw.description) opt.description = raw.description;
  return opt;
}

function toModelChoice(raw: RawOption): ModelChoice {
  const opt: ModelChoice = { id: raw.value, name: raw.name };
  if (raw.description) opt.description = raw.description;
  // features left undefined — not present in the current stream
  return opt;
}

function selectOptions(opt: SessionConfigOption): RawOption[] {
  if (opt.type !== 'select') return [];
  const raw = opt as unknown as { options?: Array<RawOption | RawOptionGroup> };
  return Array.isArray(raw.options)
    ? raw.options.flatMap((option) => ('options' in option ? option.options : [option]))
    : [];
}

/**
 * Map a raw `SessionConfigOption[]` to the three typed groups of
 * SessionConfigState: modelOptions, efforts, modeOptions.
 *
 * Category mapping:
 *   'model'         → modelOptions   (model selector)
 *   'thought_level' → efforts        (Claude effort / Codex reasoning effort)
 *   'mode'          → modeOptions    (permission mode)
 *
 * `configId` preserves the provider-owned ACP config option id, `selected` is taken from
 * `currentValue`, and `available` is the full options list.
 * Returns partial — only groups present in `options` are set; others stay null.
 * The runtime merges this partial into the existing SessionConfigState.
 */
export function deriveConfigGroups(
  options: ReadonlyArray<SessionConfigOption>
): Pick<SessionConfigState, 'modelOptions' | 'efforts' | 'modeOptions'> {
  let modelOptions: SessionConfigState['modelOptions'] = null;
  let efforts: SessionConfigState['efforts'] = null;
  let modeOptions: SessionConfigState['modeOptions'] = null;

  for (const opt of options) {
    if (opt.type !== 'select') continue;
    const rawSelected = (opt as unknown as { currentValue?: string }).currentValue ?? null;
    const rawOptions = selectOptions(opt);

    switch (opt.category) {
      case 'model':
        modelOptions = {
          configId: opt.id,
          selected: rawSelected,
          available: rawOptions.map(toModelChoice),
        };
        break;
      case 'thought_level':
        efforts = {
          configId: opt.id,
          selected: rawSelected,
          available: rawOptions.map(toEffortOption),
        };
        break;
      case 'mode':
        modeOptions = {
          configId: opt.id,
          selected: rawSelected,
          available: rawOptions.map(toModeOption),
        };
        break;
      // Unknown categories (e.g. 'model_config') are ignored — extension point.
    }
  }

  return { modelOptions, efforts, modeOptions };
}

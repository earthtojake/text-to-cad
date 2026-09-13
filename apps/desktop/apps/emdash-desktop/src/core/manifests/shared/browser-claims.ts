import {
  chordParts,
  detectPlatformContext,
  resolveEffectiveChord,
  type Chord,
  type PlatformContext,
} from '@core/primitives/keybindings/api';
import type { AppSettings } from '@core/services/settings/api';
import { COMMAND_CATALOG } from './command-catalog';

export interface BrowserClaim {
  readonly commandId: string;
  readonly chord: Chord;
}

export function buildBrowserClaims(
  keyboard: AppSettings['keyboard'] = {},
  context: PlatformContext = detectPlatformContext()
): readonly BrowserClaim[] {
  return COMMAND_CATALOG.defs.flatMap((command) => {
    const binding = command.keybinding;
    if (
      !binding ||
      binding.options?.ignoreWhenBrowserFocused ||
      binding.options?.ignoreWhenTextInputFocused
    ) {
      return [];
    }

    const effective = resolveEffectiveChord(binding, keyboard, context);
    if (!effective || chordParts(effective).key === 'Escape') return [];
    return [{ commandId: command.id, chord: effective }];
  });
}

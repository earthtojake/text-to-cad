import {
  chord,
  code,
  detectPlatformContext,
  type Chord,
  type ChordKeyboardEventLike,
  type Modifier,
  type PlatformContext,
} from '../api/chord';
import type { KeybindingOptions } from '../api/define-keybinding';
import { isKeyCode } from '../api/key-codes';

export interface KeybindingFocusContext {
  readonly textInputFocused: boolean;
  readonly editorFocused: boolean;
  readonly terminalFocused: boolean;
  readonly browserFocused: boolean;
}

interface MatchableTarget {
  matches(selector: string): boolean;
}

function hasMatches(value: unknown): value is MatchableTarget {
  return (
    typeof value === 'object' &&
    value !== null &&
    'matches' in value &&
    typeof value.matches === 'function'
  );
}

export function isTextInputFocusTarget(target: unknown): boolean {
  return (
    hasMatches(target) &&
    target.matches('input,select,textarea,[contenteditable]:not([contenteditable="false"])')
  );
}

export function shouldIgnoreForOptions(
  event: ChordKeyboardEventLike,
  options: KeybindingOptions | undefined,
  focus: KeybindingFocusContext,
  context: PlatformContext = detectPlatformContext()
): boolean {
  if (event.isComposing) return true;
  if (event.repeat && !options?.allowRepeat) return true;
  if (options?.ignoreWhenTextInputFocused && focus.textInputFocused) return true;
  if (options?.ignoreWhenEditorFocused && focus.editorFocused) return true;
  if (focus.terminalFocused && context.os !== 'mac' && !options?.allowWhenTerminalFocused) {
    return true;
  }
  return Boolean(options?.ignoreWhenBrowserFocused && focus.browserFocused);
}

const MODIFIER_KEYS = new Set(['Alt', 'Control', 'Meta', 'Shift']);

function captureModifiers(event: ChordKeyboardEventLike, context: PlatformContext): Modifier[] {
  const modifiers: Modifier[] = [];
  const primaryPressed = context.os === 'mac' ? event.metaKey : event.ctrlKey;
  if (primaryPressed) modifiers.push('Mod');
  if (event.ctrlKey && context.os === 'mac') modifiers.push('Control');
  if (event.metaKey && context.os !== 'mac') modifiers.push('Meta');
  if (event.altKey) modifiers.push('Alt');
  if (event.shiftKey) modifiers.push('Shift');
  return modifiers;
}

/**
 * Converts a recorder keydown into a portable, canonical chord. Printable keys
 * use physical code tokens so the binding remains stable across layouts.
 */
export function chordFromCaptureEvent(
  event: ChordKeyboardEventLike,
  context: PlatformContext = detectPlatformContext()
): Chord | null {
  if (event.isComposing || MODIFIER_KEYS.has(event.key)) return null;

  const modifiers = captureModifiers(event, context);
  if ((event.key.length === 1 || event.key === ' ') && isKeyCode(event.code)) {
    return code(modifiers, event.code);
  }

  try {
    return chord([...modifiers, event.key].join('+'));
  } catch {
    return null;
  }
}

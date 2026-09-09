import {
  chordParts,
  detectPlatformContext,
  tokenKind,
  type Chord,
  type PlatformContext,
} from './chord';
import { codeToChar, CODE_TO_US_CHAR, type KeyCode } from './key-codes';

export interface ElectronKeyInput {
  readonly type: string;
  readonly key: string;
  readonly code?: string;
  readonly control?: boolean;
  readonly shift?: boolean;
  readonly alt?: boolean;
  readonly meta?: boolean;
}

export type TabNavigationDirection = 'next' | 'previous';

export function matchesElectronInput(
  input: ElectronKeyInput,
  value: Chord,
  context: PlatformContext = detectPlatformContext()
): boolean {
  if (input.type !== 'keyDown' && input.type !== 'rawKeyDown') return false;
  const parts = chordParts(value);
  const expected = {
    control: parts.modifiers.includes('Control'),
    shift: parts.modifiers.includes('Shift'),
    alt: parts.modifiers.includes('Alt'),
    meta: parts.modifiers.includes('Meta'),
  };
  if (parts.modifiers.includes('$mod')) {
    if (context.os === 'mac') expected.meta = true;
    else expected.control = true;
  }
  if (
    Boolean(input.control) !== expected.control ||
    Boolean(input.shift) !== expected.shift ||
    Boolean(input.alt) !== expected.alt ||
    Boolean(input.meta) !== expected.meta
  ) {
    return false;
  }

  if (tokenKind(value) === 'code') {
    if (input.code?.toLowerCase() === parts.key.toLowerCase()) return true;
    const fallback = codeToChar(CODE_TO_US_CHAR, parts.key as KeyCode);
    return fallback !== undefined && input.key.toLowerCase() === fallback.toLowerCase();
  }
  return input.key.toLowerCase() === parts.key.toLowerCase();
}

export function getElectronTabNavigationDirection(
  input: ElectronKeyInput
): TabNavigationDirection | null {
  if (input.type !== 'keyDown' && input.type !== 'rawKeyDown') return null;
  if (input.key.toLowerCase() !== 'tab') return null;
  if (!input.control || input.alt || input.meta) return null;
  return input.shift ? 'previous' : 'next';
}

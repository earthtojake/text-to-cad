import { parseKeybinding, type KeybindingPress } from 'tinykeys';
import {
  CODE_TO_US_CHAR,
  codeToChar,
  isKeyCode,
  KEY_CODES,
  type CodeToCharMap,
  type KeyCode,
} from './key-codes';

declare const chordBrand: unique symbol;

export type Chord = string & { readonly [chordBrand]: true };
export type ChordTokenKind = 'char' | 'code' | 'named';
export type Modifier = 'Mod' | 'Control' | 'Alt' | 'Shift' | 'Meta';

export interface ChordParts {
  readonly modifiers: readonly ('$mod' | 'Control' | 'Alt' | 'Shift' | 'Meta')[];
  readonly key: string;
}

export interface ChordKeyboardEventLike {
  readonly key: string;
  readonly code: string;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
  readonly repeat: boolean;
  readonly isComposing: boolean;
}

export interface PlatformContext {
  readonly os: 'mac' | 'windows' | 'linux';
}

export type ChordSpec =
  | string
  | { readonly mac: string; readonly other: string }
  | ((context: PlatformContext) => string);

const CANONICAL_MODIFIER_ORDER = ['$mod', 'Control', 'Alt', 'Shift', 'Meta'] as const;
const MODIFIER_ALIASES: Readonly<Record<string, (typeof CANONICAL_MODIFIER_ORDER)[number]>> = {
  $mod: '$mod',
  mod: '$mod',
  control: 'Control',
  ctrl: 'Control',
  alt: 'Alt',
  option: 'Alt',
  shift: 'Shift',
  meta: 'Meta',
  cmd: 'Meta',
  command: 'Meta',
};
const NAMED_KEYS = [
  'Alt',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'ArrowUp',
  'Backspace',
  'CapsLock',
  'ContextMenu',
  'Control',
  'Delete',
  'End',
  'Enter',
  'Escape',
  'Help',
  'Home',
  'Insert',
  'Meta',
  'NumLock',
  'PageDown',
  'PageUp',
  'Pause',
  'PrintScreen',
  'ScrollLock',
  'Shift',
  'Tab',
  ...Array.from({ length: 24 }, (_, index) => `F${index + 1}`),
] as const;
const NAMED_KEY_BY_LOWER = new Map(NAMED_KEYS.map((key) => [key.toLowerCase(), key]));
const KEY_CODE_BY_LOWER = new Map(KEY_CODES.map((key) => [key.toLowerCase(), key]));
const SHIFTED_CHARACTERS = new Set('~!@#$%^&*()_+{}|:"<>?'.split(''));
const PARSED_CHORDS = new Map<Chord, KeybindingPress>();

function canonicalModifier(value: string): (typeof CANONICAL_MODIFIER_ORDER)[number] {
  const modifier = MODIFIER_ALIASES[value.toLowerCase()];
  if (!modifier) {
    throw new Error(`Unknown chord modifier: ${value}`);
  }
  return modifier;
}

function canonicalCharacter(value: string): string {
  const upper = value.toLocaleUpperCase();
  return upper.length === 1 ? upper : value;
}

function canonicalMainKey(value: string): string {
  if (value.length === 1) {
    if (SHIFTED_CHARACTERS.has(value)) {
      throw new Error(
        `Shifted character "${value}" is not a direct key; use its code token with Shift`
      );
    }
    return canonicalCharacter(value);
  }

  const named = NAMED_KEY_BY_LOWER.get(value.toLowerCase());
  if (named) return named;

  const keyCode = KEY_CODE_BY_LOWER.get(value.toLowerCase());
  if (keyCode) return keyCode;

  throw new Error(`Unknown chord key token: ${value}`);
}

function parseSourceChord(value: string): ChordParts {
  const input = value.trim();
  if (input.length === 0) {
    throw new Error('A chord must not be empty');
  }
  if (/\s/u.test(input)) {
    throw new Error('Chord sequences are not supported');
  }

  const parts = input.split(/(?<=[\w\]])\+/u);
  const rawKey = parts.pop();
  if (!rawKey) {
    throw new Error(`Chord "${value}" has no main key`);
  }

  const modifiers = parts.map(canonicalModifier);
  if (new Set(modifiers).size !== modifiers.length) {
    throw new Error(`Chord "${value}" contains duplicate modifiers`);
  }
  modifiers.sort(
    (left, right) =>
      CANONICAL_MODIFIER_ORDER.indexOf(left) - CANONICAL_MODIFIER_ORDER.indexOf(right)
  );

  const key = canonicalMainKey(rawKey);
  if (modifiers.includes('Alt') && key.length === 1) {
    throw new Error('Chords combining Alt with a printable key must use a code token');
  }

  return { modifiers, key };
}

function canonicalString(parts: ChordParts): string {
  return [...parts.modifiers, parts.key].join('+');
}

export function chord(value: string): Chord {
  const canonical = canonicalString(parseSourceChord(value)) as Chord;
  const parsed = parseKeybinding(canonical);
  if (parsed.length !== 1 || parsed[0]?.[2] instanceof RegExp) {
    throw new Error(`Invalid chord: ${value}`);
  }
  return canonical;
}

export function isValidChord(value: string): boolean {
  try {
    chord(value);
    return true;
  } catch {
    return false;
  }
}

export function chordParts(value: Chord): ChordParts {
  return parseSourceChord(value);
}

export function tokenKind(value: Chord): ChordTokenKind {
  const { key } = chordParts(value);
  if (NAMED_KEY_BY_LOWER.has(key.toLowerCase())) return 'named';
  return isKeyCode(key) ? 'code' : 'char';
}

export function code(modifiers: readonly Modifier[], key: KeyCode): Chord {
  return chord([...modifiers, key].join('+'));
}

export function parseChord(value: Chord): KeybindingPress {
  const cached = PARSED_CHORDS.get(value);
  if (cached) return cached;

  const parsed = parseKeybinding(value)[0];
  if (!parsed) {
    throw new Error(`Invalid chord: ${value}`);
  }
  PARSED_CHORDS.set(value, parsed);
  return parsed;
}

export function chordsEqual(left: Chord, right: Chord): boolean {
  return left === right;
}

export function translateCodeChord(value: Chord, map: CodeToCharMap): Chord | null {
  if (tokenKind(value) !== 'code') return null;

  const parts = chordParts(value);
  const mapped = codeToChar(map, parts.key as KeyCode);
  if (!mapped) return null;

  try {
    return chord(canonicalString({ ...parts, key: mapped }));
  } catch {
    return null;
  }
}

// Structural declaration keeps this isomorphic api file free of node ambient
// types; the typeof guard below already handles environments without it.
declare const process: { platform?: string } | undefined;

export function detectPlatformContext(): PlatformContext {
  if (typeof navigator !== 'undefined') {
    const platform = `${navigator.platform} ${navigator.userAgent}`;
    if (/Mac|iPhone|iPad|iPod/iu.test(platform)) return { os: 'mac' };
    if (/Win/iu.test(platform)) return { os: 'windows' };
  }

  if (typeof process !== 'undefined') {
    if (process.platform === 'darwin') return { os: 'mac' };
    if (process.platform === 'win32') return { os: 'windows' };
  }

  return { os: 'linux' };
}

export function resolveChordSpec(
  spec: ChordSpec,
  context: PlatformContext = detectPlatformContext()
): Chord {
  if (typeof spec === 'string') return chord(spec);
  if (typeof spec === 'function') return chord(spec(context));
  return chord(context.os === 'mac' ? spec.mac : spec.other);
}

const ELECTRON_KEY_NAMES: Readonly<Record<string, string>> = {
  ArrowDown: 'Down',
  ArrowLeft: 'Left',
  ArrowRight: 'Right',
  ArrowUp: 'Up',
};

export function toElectronAccelerator(value: Chord): string {
  const parts = chordParts(value);
  const modifiers = parts.modifiers.map((modifier) => {
    if (modifier === '$mod') return 'CmdOrCtrl';
    if (modifier === 'Control') return 'Ctrl';
    if (modifier === 'Meta') return 'Command';
    return modifier;
  });

  let key = parts.key;
  if (tokenKind(value) === 'code') {
    key = codeToChar(CODE_TO_US_CHAR, key as KeyCode) ?? key;
  }
  key = ELECTRON_KEY_NAMES[key] ?? canonicalCharacter(key);
  return [...modifiers, key].join('+');
}

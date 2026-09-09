import { chord, resolveChordSpec, type Chord, type ChordSpec, type PlatformContext } from './chord';

export interface KeybindingOptions {
  readonly ignoreWhenTextInputFocused?: boolean;
  readonly ignoreWhenEditorFocused?: boolean;
  readonly ignoreWhenBrowserFocused?: boolean;
  readonly allowWhenTerminalFocused?: boolean;
  readonly allowRepeat?: boolean;
}

export interface FixedKeybinding {
  readonly kind: 'fixed';
  readonly chord: ChordSpec;
  readonly options?: KeybindingOptions;
}

export interface SettingsKeybinding<TSettingsKey extends string = string> {
  readonly kind: 'settings';
  readonly settingsKey: TSettingsKey;
  readonly defaultChord: ChordSpec;
  readonly options?: KeybindingOptions;
}

export type Keybinding<TSettingsKey extends string = string> =
  | FixedKeybinding
  | SettingsKeybinding<TSettingsKey>;

export type ChordOverrides = Readonly<Partial<Record<string, string | null>>>;

function normalizeChordSpec(spec: ChordSpec): ChordSpec {
  if (typeof spec === 'string') return chord(spec);
  if (typeof spec === 'function') return spec;
  return Object.freeze({
    mac: chord(spec.mac),
    other: chord(spec.other),
  });
}

function freezeOptions(options: KeybindingOptions | undefined): KeybindingOptions | undefined {
  return options ? Object.freeze({ ...options }) : undefined;
}

export const keybinding = Object.freeze({
  fixed(chordSpec: ChordSpec, options?: KeybindingOptions): FixedKeybinding {
    return Object.freeze({
      kind: 'fixed',
      chord: normalizeChordSpec(chordSpec),
      options: freezeOptions(options),
    });
  },

  settings<const TSettingsKey extends string>(
    settingsKey: TSettingsKey,
    defaultChord: ChordSpec,
    options?: KeybindingOptions
  ): SettingsKeybinding<TSettingsKey> {
    if (settingsKey.trim().length === 0) {
      throw new Error('A keybinding settings key must not be empty');
    }
    return Object.freeze({
      kind: 'settings',
      settingsKey,
      defaultChord: normalizeChordSpec(defaultChord),
      options: freezeOptions(options),
    });
  },
});

function resolveStoredOverride(value: string): Chord | undefined {
  try {
    return chord(value);
  } catch {
    return undefined;
  }
}

export function resolveEffectiveChord(
  binding: Keybinding,
  overrides: ChordOverrides,
  context: PlatformContext
): Chord | null {
  if (binding.kind === 'fixed') {
    return resolveChordSpec(binding.chord, context);
  }

  const override = overrides[binding.settingsKey];
  if (override === null) return null;
  if (override !== undefined) {
    const resolved = resolveStoredOverride(override);
    if (resolved) return resolved;
  }
  return resolveChordSpec(binding.defaultChord, context);
}

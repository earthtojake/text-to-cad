import { computed, observable, type IComputedValue, type IObservableValue } from 'mobx';
import type { KeybindingPress } from 'tinykeys';
import { COMMAND_CATALOG } from '@core/manifests/shared/command-catalog';
import { MENU_ITEMS } from '@core/manifests/shared/menu-items';
import type { CommandDef } from '@core/primitives/commands/api';
import {
  detectPlatformContext,
  parseChord,
  resolveEffectiveChord,
  toElectronAccelerator,
  type Chord,
  type ChordOverrides,
  type KeybindingOptions,
  type PlatformContext,
  type SettingsKeybinding,
} from '@core/primitives/keybindings/api';

export interface ResolvedKeybindingEntry {
  readonly command: CommandDef;
  readonly chord: Chord;
  readonly press: KeybindingPress;
  readonly options: KeybindingOptions | undefined;
}

export interface SettingsKeybindingEntry {
  readonly command: CommandDef;
  readonly binding: SettingsKeybinding;
  readonly chord: Chord | null;
  readonly defaultChord: Chord;
}

export interface SettingsKeybindingGroup {
  readonly category: string;
  readonly entries: readonly SettingsKeybindingEntry[];
}

export interface MenuKeybindingSnapshotEntry {
  readonly commandId: string;
  readonly title: string;
  readonly accelerator: string | null;
}

export class KeybindingService {
  private readonly definitions: readonly CommandDef[];
  private readonly menuDefinitions: readonly CommandDef[];
  private readonly context: PlatformContext;
  private readonly overridesValue: IObservableValue<ChordOverrides>;
  private readonly entriesValue: IComputedValue<readonly ResolvedKeybindingEntry[]>;

  constructor(
    definitions: readonly CommandDef[] = COMMAND_CATALOG.defs,
    context: PlatformContext = detectPlatformContext(),
    menuDefinitions: readonly CommandDef[] = MENU_ITEMS
  ) {
    this.definitions = definitions;
    const definitionIds = new Set(definitions.map((definition) => definition.id));
    this.menuDefinitions = menuDefinitions.filter((definition) => definitionIds.has(definition.id));
    this.context = context;
    this.overridesValue = observable.box({}, { deep: false });
    this.entriesValue = computed(() => this.computeEntries());
  }

  get entries(): readonly ResolvedKeybindingEntry[] {
    return this.entriesValue.get();
  }

  chordFor(commandId: string): Chord | null {
    return this.entries.find((entry) => entry.command.id === commandId)?.chord ?? null;
  }

  settingsEntries(): readonly SettingsKeybindingGroup[] {
    const groups = new Map<string, SettingsKeybindingEntry[]>();
    for (const command of this.definitions) {
      const binding = command.keybinding;
      if (binding?.kind !== 'settings') continue;
      const entries = groups.get(command.category) ?? [];
      entries.push(
        Object.freeze({
          command,
          binding,
          chord: this.chordFor(command.id),
          defaultChord: resolveEffectiveChord(binding, {}, this.context)!,
        })
      );
      groups.set(command.category, entries);
    }
    return Object.freeze(
      [...groups].map(([category, entries]) =>
        Object.freeze({ category, entries: Object.freeze(entries) })
      )
    );
  }

  snapshotForMenu(): readonly MenuKeybindingSnapshotEntry[] {
    return Object.freeze(
      this.menuDefinitions.map((command) => {
        const chord = this.chordFor(command.id);
        return Object.freeze({
          commandId: command.id,
          title: command.title,
          accelerator: chord ? toElectronAccelerator(chord) : null,
        });
      })
    );
  }

  setOverrides(overrides: ChordOverrides | undefined): void {
    this.overridesValue.set(Object.freeze({ ...(overrides ?? {}) }));
  }

  private computeEntries(): readonly ResolvedKeybindingEntry[] {
    const overrides = this.overridesValue.get();
    const entries: ResolvedKeybindingEntry[] = [];

    for (const command of this.definitions) {
      const binding = command.keybinding;
      if (!binding) continue;
      const chord = resolveEffectiveChord(binding, overrides, this.context);
      if (!chord) continue;
      entries.push(
        Object.freeze({
          command,
          chord,
          press: parseChord(chord),
          options: binding.options,
        })
      );
    }

    return Object.freeze(entries);
  }
}

export const keybindingService = new KeybindingService();

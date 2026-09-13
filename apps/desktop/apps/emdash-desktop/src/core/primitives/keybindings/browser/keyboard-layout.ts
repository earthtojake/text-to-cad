import { createEmitter, type Unsubscribe } from '@emdash/shared';
import {
  chordParts,
  detectPlatformContext,
  tokenKind,
  type Chord,
  type PlatformContext,
} from '../api/chord';
import { CODE_TO_US_CHAR, codeToChar, type KeyCode } from '../api/key-codes';

export interface KeyboardLayoutApi {
  getLayoutMap(): Promise<Iterable<readonly [string, string]>>;
  addEventListener?(type: 'layoutchange', listener: () => void): void;
  removeEventListener?(type: 'layoutchange', listener: () => void): void;
}

const MAIN_KEY_LABELS: Readonly<Record<string, string>> = {
  ArrowDown: '↓',
  ArrowLeft: '←',
  ArrowRight: '→',
  ArrowUp: '↑',
  Backspace: '⌫',
  Delete: 'Del',
  Enter: '⏎',
  Escape: 'Esc',
  PageDown: 'PgDn',
  PageUp: 'PgUp',
  Space: 'Space',
  Tab: 'Tab',
};

function modifierLabel(
  modifier: '$mod' | 'Control' | 'Alt' | 'Shift' | 'Meta',
  context: PlatformContext
): string {
  if (context.os === 'mac') {
    return (
      {
        $mod: '⌘',
        Alt: '⌥',
        Control: '⌃',
        Meta: '⌘',
        Shift: '⇧',
      } as const
    )[modifier];
  }

  return (
    {
      $mod: 'Ctrl',
      Alt: 'Alt',
      Control: 'Ctrl',
      Meta: context.os === 'windows' ? 'Win' : 'Meta',
      Shift: 'Shift',
    } as const
  )[modifier];
}

function modifierOrder(
  modifier: '$mod' | 'Control' | 'Alt' | 'Shift' | 'Meta',
  context: PlatformContext
): number {
  const resolved = modifier === '$mod' ? (context.os === 'mac' ? 'Meta' : 'Control') : modifier;
  const order =
    context.os === 'mac'
      ? { Control: 0, Alt: 1, Meta: 2, Shift: 3 }
      : { Control: 0, Alt: 1, Shift: 2, Meta: 3 };
  return order[resolved];
}

function displayMainKey(value: string): string {
  if (MAIN_KEY_LABELS[value]) return MAIN_KEY_LABELS[value];
  const upper = value.toLocaleUpperCase();
  return value.length === 1 && upper.length === 1 ? upper : value;
}

export class KeyboardLayoutService {
  private readonly didChangeEmitter = createEmitter<void>();
  private readonly handleNativeChange = () => {
    this.pendingLoad = this.load();
  };
  private layoutMap: ReadonlyMap<string, string> | undefined;
  private pendingLoad: Promise<void>;

  constructor(private readonly keyboardApi: KeyboardLayoutApi | undefined) {
    keyboardApi?.addEventListener?.('layoutchange', this.handleNativeChange);
    this.pendingLoad = this.load();
  }

  whenReady(): Promise<void> {
    return this.pendingLoad;
  }

  displayLabel(value: Chord, context: PlatformContext = detectPlatformContext()): string[] {
    const parts = chordParts(value);
    const modifiers = [...parts.modifiers]
      .sort((left, right) => modifierOrder(left, context) - modifierOrder(right, context))
      .map((modifier) => modifierLabel(modifier, context));

    let mainKey = parts.key;
    if (tokenKind(value) === 'code') {
      mainKey =
        this.layoutMap?.get(parts.key) ??
        codeToChar(CODE_TO_US_CHAR, parts.key as KeyCode) ??
        parts.key;
    }

    return [...modifiers, displayMainKey(mainKey)];
  }

  codeToCharMap(): ReadonlyMap<string, string> | undefined {
    return this.layoutMap;
  }

  onDidChangeLayout(listener: () => void): Unsubscribe {
    return this.didChangeEmitter.subscribe(listener);
  }

  dispose(): void {
    this.keyboardApi?.removeEventListener?.('layoutchange', this.handleNativeChange);
    this.didChangeEmitter.clear();
  }

  private async load(): Promise<void> {
    if (!this.keyboardApi) return;

    try {
      this.layoutMap = new Map(await this.keyboardApi.getLayoutMap());
      this.didChangeEmitter.emit();
    } catch {
      // Layout discovery is best-effort; callers keep using US-reference labels.
    }
  }
}

type NavigatorWithKeyboard = Navigator & { readonly keyboard?: KeyboardLayoutApi };

export function createKeyboardLayoutService(): KeyboardLayoutService {
  const keyboard =
    typeof navigator === 'undefined' ? undefined : (navigator as NavigatorWithKeyboard).keyboard;
  return new KeyboardLayoutService(keyboard);
}

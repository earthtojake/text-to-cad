import { describe, expect, it, vi } from 'vitest';
import { chord, code } from '../api/chord';
import { KeyboardLayoutService, type KeyboardLayoutApi } from './keyboard-layout';

class FakeKeyboardApi implements KeyboardLayoutApi {
  private readonly listeners = new Set<() => void>();

  constructor(public entries: readonly (readonly [string, string])[]) {}

  async getLayoutMap(): Promise<Iterable<readonly [string, string]>> {
    return this.entries;
  }

  addEventListener(_type: 'layoutchange', listener: () => void): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: 'layoutchange', listener: () => void): void {
    this.listeners.delete(listener);
  }

  emitChange(): void {
    for (const listener of this.listeners) listener();
  }
}

describe('KeyboardLayoutService', () => {
  it('translates code-token labels using the current layout', async () => {
    const api = new FakeKeyboardApi([['BracketLeft', 'ü']]);
    const service = new KeyboardLayoutService(api);
    await service.whenReady();

    expect(service.displayLabel(code(['Mod'], 'BracketLeft'), { os: 'mac' })).toEqual(['⌘', 'Ü']);
    expect(service.codeToCharMap()?.get('BracketLeft')).toBe('ü');
  });

  it('uses US-reference labels before loading and without the keyboard API', () => {
    let resolveLayout: ((entries: Iterable<readonly [string, string]>) => void) | undefined;
    const pendingApi: KeyboardLayoutApi = {
      getLayoutMap: () =>
        new Promise((resolve) => {
          resolveLayout = resolve;
        }),
    };
    const pending = new KeyboardLayoutService(pendingApi);
    const unavailable = new KeyboardLayoutService(undefined);

    expect(pending.displayLabel(code(['Mod'], 'BracketLeft'), { os: 'mac' })).toEqual(['⌘', '[']);
    expect(unavailable.displayLabel(code(['Mod'], 'BracketLeft'), { os: 'linux' })).toEqual([
      'Ctrl',
      '[',
    ]);
    expect(pending.codeToCharMap()).toBeUndefined();

    resolveLayout?.([]);
  });

  it('leaves char and named tokens independent of the layout map', async () => {
    const service = new KeyboardLayoutService(
      new FakeKeyboardApi([
        ['KeyK', 'л'],
        ['ArrowLeft', 'unexpected'],
      ])
    );
    await service.whenReady();

    expect(service.displayLabel(chord('Mod+K'), { os: 'windows' })).toEqual(['Ctrl', 'K']);
    expect(service.displayLabel(chord('Mod+ArrowLeft'), { os: 'windows' })).toEqual(['Ctrl', '←']);
  });

  it('refreshes the map and notifies subscribers after a layout change', async () => {
    const api = new FakeKeyboardApi([['BracketLeft', '[']]);
    const service = new KeyboardLayoutService(api);
    await service.whenReady();
    const listener = vi.fn();
    const unsubscribe = service.onDidChangeLayout(listener);

    api.entries = [['BracketLeft', 'ü']];
    api.emitChange();
    await service.whenReady();

    expect(service.displayLabel(code([], 'BracketLeft'), { os: 'linux' })).toEqual(['Ü']);
    expect(listener).toHaveBeenCalledOnce();

    unsubscribe();
    service.dispose();
    api.entries = [['BracketLeft', 'å']];
    api.emitChange();
    expect(listener).toHaveBeenCalledOnce();
  });
});

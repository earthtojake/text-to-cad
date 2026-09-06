import { SearchInput } from '@emdash/ui/react/primitives';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { detectPlatformContext } from '@core/primitives/keybindings/api';
import {
  useSearchFocusHotkeys,
  type UseSearchFocusHotkeysOptions,
} from '@core/primitives/keybindings/browser';
import { Shortcut } from '@core/primitives/keybindings/browser/shortcut';

const PLATFORM = detectPlatformContext().os;

/** Settings-style composition: @emdash/ui SearchInput wired to the app focus hotkeys. */
function SettingsSearch({
  label = 'Search settings',
  ...options
}: UseSearchFocusHotkeysOptions & { label?: string }) {
  const searchRef = useSearchFocusHotkeys(options);
  return (
    <SearchInput
      ref={searchRef}
      aria-label={label}
      placeholder="Search settings"
      shortcut={<Shortcut hotkey="Mod+F" variant="keycaps" />}
    />
  );
}

function dispatchShortcut(init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent('keydown', {
    bubbles: true,
    cancelable: true,
    ...init,
  });
  (document.activeElement ?? document).dispatchEvent(event);
  return event;
}

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('settings search shortcuts', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  async function renderSearch(): Promise<HTMLInputElement> {
    await act(async () => {
      root.render(
        <>
          <button type="button">Before search</button>
          <textarea aria-label="Notes" />
          <SettingsSearch focusHotkey focusSlashHotkey />
        </>
      );
    });
    return host.querySelector<HTMLInputElement>('[aria-label="Search settings"]')!;
  }

  it('focuses settings search and prevents native find on Mod+F', async () => {
    const search = await renderSearch();
    host.querySelector<HTMLButtonElement>('button')!.focus();

    const event = dispatchShortcut({
      key: 'f',
      code: 'KeyF',
      ctrlKey: PLATFORM !== 'mac',
      metaKey: PLATFORM === 'mac',
    });

    expect(document.activeElement).toBe(search);
    expect(event.defaultPrevented).toBe(true);
  });

  it('shows the platform Mod-F shortcut as matching keycaps', async () => {
    await renderSearch();

    expect(Array.from(host.querySelectorAll('kbd')).map((keycap) => keycap.textContent)).toEqual([
      PLATFORM === 'mac' ? '⌘' : 'Ctrl',
      'F',
    ]);
  });

  it('allows a nested search field to opt out of owning Mod+F', async () => {
    await act(async () => {
      root.render(
        <>
          <button type="button">Before search</button>
          <SettingsSearch label="Nested search" focusHotkey={false} />
        </>
      );
    });
    const beforeSearch = host.querySelector<HTMLButtonElement>('button')!;
    beforeSearch.focus();

    const event = dispatchShortcut({
      key: 'f',
      code: 'KeyF',
      ctrlKey: PLATFORM !== 'mac',
      metaKey: PLATFORM === 'mac',
    });

    expect(document.activeElement).toBe(beforeSearch);
    expect(event.defaultPrevented).toBe(false);
  });

  it('focuses settings search when slash is pressed outside an editable control', async () => {
    const search = await renderSearch();
    host.querySelector<HTMLButtonElement>('button')!.focus();

    const event = dispatchShortcut({ key: '/', code: 'Slash' });

    expect(document.activeElement).toBe(search);
    expect(event.defaultPrevented).toBe(true);
  });

  it('does not steal slash while the user is typing in an editable control', async () => {
    const search = await renderSearch();
    const notes = host.querySelector<HTMLTextAreaElement>('textarea')!;
    notes.focus();

    const event = dispatchShortcut({ key: '/', code: 'Slash' });

    expect(document.activeElement).toBe(notes);
    expect(document.activeElement).not.toBe(search);
    expect(event.defaultPrevented).toBe(false);
  });
});

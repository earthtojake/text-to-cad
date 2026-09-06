import * as React from 'react';
import { isTextInputFocusTarget } from './chord-from-event';
import { useChordKeydown } from './use-chord-keydown';

export interface UseSearchFocusHotkeysOptions {
  /** Focus the input on Mod+F. Disable when another search field on the page owns the hotkey. */
  focusHotkey?: boolean;
  /** Focus the input when `/` is pressed outside an editable control. */
  focusSlashHotkey?: boolean;
}

/**
 * Wires the app's search-focus hotkeys (Mod+F, optional `/`) to an input.
 * Returns a ref to attach to the input element (e.g. `@emdash/ui` SearchInput).
 */
export function useSearchFocusHotkeys({
  focusHotkey = true,
  focusSlashHotkey = false,
}: UseSearchFocusHotkeysOptions = {}): React.RefObject<HTMLInputElement | null> {
  const inputRef = React.useRef<HTMLInputElement>(null);

  useChordKeydown(
    'Mod+F',
    (event) => {
      event.preventDefault();
      inputRef.current?.focus();
    },
    { enabled: focusHotkey }
  );

  useChordKeydown(
    '/',
    (event) => {
      if (isTextInputFocusTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    },
    { enabled: focusSlashHotkey }
  );

  return inputRef;
}

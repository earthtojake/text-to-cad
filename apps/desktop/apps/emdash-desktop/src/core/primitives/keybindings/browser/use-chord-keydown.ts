import { useEffect, useRef } from 'react';
import { matchKeybindingPress } from 'tinykeys';
import {
  detectPlatformContext,
  parseChord,
  resolveChordSpec,
  type ChordSpec,
} from '@core/primitives/keybindings/api';

export interface UseChordKeydownOptions {
  readonly enabled?: boolean;
  readonly target?: EventTarget | null;
  readonly capture?: boolean;
}

/**
 * Registers component-local keyboard behavior that is not an application
 * command. App commands must be contributed through a view scope instead.
 */
export function useChordKeydown(
  chordSpec: ChordSpec,
  handler: (event: KeyboardEvent) => void,
  options: UseChordKeydownOptions = {}
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const { capture = false, enabled = true, target } = options;

  useEffect(() => {
    if (!enabled) return;
    const resolvedTarget = target ?? (typeof window === 'undefined' ? undefined : window);
    if (!resolvedTarget) return;
    const press = parseChord(resolveChordSpec(chordSpec, detectPlatformContext()));
    const onKeyDown = (event: Event) => {
      const keyboardEvent = event as KeyboardEvent;
      if (keyboardEvent.defaultPrevented) return;
      if (matchKeybindingPress(keyboardEvent, press)) {
        handlerRef.current(keyboardEvent);
      }
    };
    resolvedTarget.addEventListener('keydown', onKeyDown, { capture });
    return () => resolvedTarget.removeEventListener('keydown', onKeyDown, { capture });
  }, [capture, chordSpec, enabled, target]);
}

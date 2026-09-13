import { useEffect } from 'react';
import { getDesktopWireClient } from '@renderer/lib/runtime/desktop-wire-client';
import { keybindingDispatcher } from './keybinding-dispatcher';

export function BrowserShortcutForwarding() {
  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;

    void getDesktopWireClient().then(async (client) => {
      const nextUnsubscribe = await client.host.events.subscribe(undefined, {
        onEvent: (event) => {
          if (event.type !== 'browser-app-shortcut') return;
          keybindingDispatcher.dispatchSynthetic(new Set([event.commandId]), {
            textInputFocused: true,
            editorFocused: false,
            terminalFocused: false,
            browserFocused: true,
          });
        },
        onGap: () => {},
      });

      if (disposed) nextUnsubscribe();
      else unsubscribe = nextUnsubscribe;
    });

    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, []);

  return null;
}

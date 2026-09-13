import { isDeepEqual } from '@emdash/shared';
import { reaction } from 'mobx';
import { useEffect } from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { keybindingService } from '@core/primitives/keybindings/browser/keybinding-service';
import { getDesktopWireClient } from '@renderer/lib/runtime/desktop-wire-client';
import { keybindingDispatcher } from './keybinding-dispatcher';

export function KeybindingDispatcherMount() {
  const { value: keyboard } = useAppSettingsKey('keyboard');

  useEffect(() => {
    keybindingService.setOverrides(keyboard);
  }, [keyboard]);

  useEffect(() => keybindingDispatcher.attach(window), []);

  useEffect(() => {
    let disposed = false;
    let disposeReaction: (() => void) | undefined;
    void getDesktopWireClient().then((client) => {
      if (disposed) return;
      disposeReaction = reaction(
        () => keybindingService.snapshotForMenu(),
        (snapshot) => {
          void client.host.setMenuKeybindings([...snapshot]);
        },
        { fireImmediately: true, equals: isDeepEqual }
      );
    });
    return () => {
      disposed = true;
      disposeReaction?.();
    };
  }, []);

  return null;
}

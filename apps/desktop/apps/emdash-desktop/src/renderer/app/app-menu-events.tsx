import { toast } from '@emdash/ui/react/primitives';
import { useEffect } from 'react';
import { useRegisterNotificationOpenHandlers } from '@core/features/workbench/contributions/browser/notification-open-handlers';
import { COMMAND_CATALOG } from '@core/manifests/shared/command-catalog';
import { scopes } from '@core/primitives/view-scopes/browser';
import { getDesktopWireClient } from '@renderer/lib/runtime/desktop-wire-client';

export function AppMenuEvents({ onOpenSettings }: { onOpenSettings?: () => boolean | void }) {
  useRegisterNotificationOpenHandlers();

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void getDesktopWireClient().then(async (client) => {
      const nextUnsubscribe = await client.host.events.subscribe(undefined, {
        onEvent: (event) => {
          if (event.type === 'menu-command') {
            const command = COMMAND_CATALOG.byId(event.commandId);
            if (!command) return;
            if (command.id === 'app.settings' && onOpenSettings?.() === false) return;
            const execute = () => {
              const bound = scopes.getActiveCommand(command);
              if (!bound) return false;
              if (bound.availability.kind === 'enabled') {
                bound.execute(undefined, 'menu');
              }
              return true;
            };
            if (!execute()) {
              requestAnimationFrame(() => {
                if (!execute() && import.meta.env.DEV) {
                  console.warn(`Menu command has no active binding: ${command.id}`);
                }
              });
            }
          }
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
  }, [onOpenSettings]);

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void getDesktopWireClient().then(async (client) => {
      const nextUnsubscribe = await client.browser.events.subscribe(undefined, {
        onEvent: (event) => {
          if (event.type !== 'link-copied') return;
          const title =
            event.kind === 'url'
              ? 'Browser URL copied'
              : event.kind === 'image'
                ? 'Image URL copied'
                : 'Link copied';
          toast(title);
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

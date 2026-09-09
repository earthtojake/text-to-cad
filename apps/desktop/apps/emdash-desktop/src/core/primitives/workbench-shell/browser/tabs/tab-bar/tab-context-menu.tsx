import { ContextMenu } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import type { ReactNode } from 'react';
import { BoundShortcut, Shortcut } from '@core/primitives/keybindings/browser/shortcut';
import type { TabHost } from '@core/primitives/workbench-shell/browser/tabs/core/tab-host';
import type {
  ResolvedTab,
  TabViewContext,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import type { TabCommand } from './tab-commands';

/** Renders a shortcut hint from a command or raw chord getter. */
function CmdShortcut({ shortcut }: { shortcut?: TabCommand['shortcut'] }) {
  if (!shortcut) return null;
  if ('chord' in shortcut) {
    return <Shortcut hotkey={shortcut.chord()} className="ml-auto" />;
  }
  return <BoundShortcut command={shortcut.commandId} className="ml-auto" />;
}

/**
 * Generic context menu wrapper for any tab kind.
 *
 * Provides engine built-in commands (Keep Open, Close Tab, Close Other Tabs) and
 * appends optional kind-specific commands from `kindCommands`. Engine commands are
 * in the "close" group; kind-specific commands are separated by a divider.
 */
export const TabContextMenu = observer(function TabContextMenu({
  tab,
  host,
  ctx: _ctx,
  kindCommands = [],
  children,
}: {
  tab: ResolvedTab;
  host: TabHost;
  ctx: TabViewContext;
  kindCommands?: TabCommand[];
  children: ReactNode;
}) {
  const engineCommands: TabCommand[] = [
    ...(tab.isPreview
      ? [
          {
            id: 'engine:keep-open',
            label: 'Keep Open',
            group: 'close' as const,
            run: () => host.pin(tab.tabId),
          },
        ]
      : []),
    {
      id: 'engine:close',
      label: 'Close Tab',
      group: 'close' as const,
      run: () => host.requestCloseTab(tab.tabId),
    },
    {
      id: 'engine:close-others',
      label: 'Close Other Tabs',
      group: 'close' as const,
      run: () => host.closeOthers(tab.tabId),
    },
  ];

  const visibleEngine = engineCommands.filter((c) => c.isAvailable?.() !== false);
  const visibleKind = kindCommands.filter((c) => c.isAvailable?.() !== false);

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger className="flex h-full">{children}</ContextMenu.Trigger>
      <ContextMenu.Content finalFocus={false}>
        {visibleEngine.map((cmd) => (
          <ContextMenu.Item key={cmd.id} onClick={() => void cmd.run()}>
            {cmd.icon ? <cmd.icon className="size-4" /> : null}
            {cmd.label}
            <CmdShortcut shortcut={cmd.shortcut} />
          </ContextMenu.Item>
        ))}
        {visibleKind.length > 0 && visibleEngine.length > 0 && <ContextMenu.Separator />}
        {visibleKind.map((cmd) => (
          <ContextMenu.Item key={cmd.id} onClick={() => void cmd.run()}>
            {cmd.icon ? <cmd.icon className="size-4" /> : null}
            {cmd.label}
            <CmdShortcut shortcut={cmd.shortcut} />
          </ContextMenu.Item>
        ))}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
});

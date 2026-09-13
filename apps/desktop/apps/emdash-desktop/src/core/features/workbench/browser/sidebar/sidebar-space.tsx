import { Toggle, Tooltip } from '@emdash/ui/react/primitives';
import { PanelLeft } from 'lucide-react';
import { NavButtons } from '@core/features/workbench/browser/nav-buttons';
import { useWorkspaceLayoutContext } from '@core/features/workbench/contributions/browser/layout-provider';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';

export function SidebarSpace() {
  const { isLeftOpen, toggleLeftSidebar } = useWorkspaceLayoutContext();
  return (
    <div className="flex h-10 w-full items-center justify-end gap-2 px-2 [-webkit-app-region:drag]">
      <NavButtons />
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Toggle
              className="[-webkit-app-region:no-drag]"
              size="sm"
              icon
              pressed={isLeftOpen}
              onPressedChange={() => toggleLeftSidebar()}
            >
              <PanelLeft className="h-4 w-4" />
            </Toggle>
          }
        />
        <Tooltip.Content>
          Toggle left sidebar
          <BoundShortcut command="workbench.toggleLeftSidebar" variant="keycaps" />
        </Tooltip.Content>
      </Tooltip.Root>
    </div>
  );
}

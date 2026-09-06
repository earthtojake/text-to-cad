import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { PanelLeft } from 'lucide-react';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import { NavButtons } from './nav-buttons';

export function SidebarRecoveryControls({ onShowSidebar }: { onShowSidebar: () => void }) {
  return (
    <div className="ml-2 flex items-center gap-0.5 [-webkit-app-region:no-drag]">
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              aria-label="Show left sidebar"
              onClick={onShowSidebar}
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          }
        />
        <Tooltip.Content>
          Show left sidebar
          <BoundShortcut command="workbench.toggleLeftSidebar" variant="keycaps" />
        </Tooltip.Content>
      </Tooltip.Root>
      <NavButtons />
    </div>
  );
}

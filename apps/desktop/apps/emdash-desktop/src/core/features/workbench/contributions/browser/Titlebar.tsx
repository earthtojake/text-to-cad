import { type ReactNode } from 'react';
import { SidebarRecoveryControls } from '@core/features/workbench/browser/sidebar-recovery-controls';
import { WindowControls } from '@core/features/workbench/browser/window-controls';
import { useWorkspaceLayoutContext } from '@core/features/workbench/contributions/browser/layout-provider';
import { detectPlatformContext } from '@core/primitives/keybindings/api';
import { cn } from '@core/primitives/styling/browser/cn';

const platform = detectPlatformContext().os;
const isMac = platform === 'mac';
const isLinux = platform === 'linux';

export function Titlebar({
  leftSlot,
  rightSlot,
  showSidebarRecovery = true,
}: {
  leftSlot?: ReactNode;
  rightSlot?: ReactNode;
  showSidebarRecovery?: boolean;
}) {
  const { toggleLeftSidebar, isLeftOpen } = useWorkspaceLayoutContext();
  return (
    <header
      className={cn(
        'flex h-10 shrink-0 items-center bg-background-secondary border-b border-border [-webkit-app-region:drag]',
        // macOS traffic lights sit at the top-left, so clear room only there.
        !isLeftOpen && isMac && 'pl-18',
        // Linux draws its own controls flush to the right corner (no native
        // frame); everywhere else keep the normal right padding.
        isLinux ? 'pr-0' : 'pr-2'
      )}
    >
      <div className="pointer-events-auto flex min-w-0 flex-1 items-center gap-1">
        <div className="flex w-full min-w-0 items-center justify-between">
          <div className="flex min-w-0 flex-1 items-center justify-start overflow-hidden [-webkit-app-region:no-drag]">
            {!isLeftOpen && showSidebarRecovery ? (
              <SidebarRecoveryControls onShowSidebar={toggleLeftSidebar} />
            ) : null}
            {leftSlot}
          </div>
          <div className="flex shrink-0 items-center justify-end gap-1 [-webkit-app-region:no-drag]">
            {rightSlot}
          </div>
        </div>
      </div>
      {isLinux && <WindowControls />}
    </header>
  );
}

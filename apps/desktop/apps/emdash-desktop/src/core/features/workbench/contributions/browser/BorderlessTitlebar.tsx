import { SidebarRecoveryControls } from '@core/features/workbench/browser/sidebar-recovery-controls';
import { WindowControls } from '@core/features/workbench/browser/window-controls';
import { useWorkspaceLayoutContext } from '@core/features/workbench/contributions/browser/layout-provider';
import { detectPlatformContext } from '@core/primitives/keybindings/api';
import { cn } from '@core/primitives/styling/browser/cn';

const platform = detectPlatformContext().os;
const isMac = platform === 'mac';
const isLinux = platform === 'linux';

export function BorderlessTitlebar() {
  const { isLeftOpen, toggleLeftSidebar } = useWorkspaceLayoutContext();

  return (
    <header
      data-borderless-titlebar
      className={cn(
        'absolute inset-x-0 top-0 z-20 flex h-10 items-center bg-background [-webkit-app-region:drag]',
        !isLeftOpen && isMac && 'pl-18',
        isLinux ? 'pr-0' : 'pr-2'
      )}
    >
      <div className="flex min-w-0 flex-1 items-center">
        {!isLeftOpen && <SidebarRecoveryControls onShowSidebar={toggleLeftSidebar} />}
      </div>
      {isLinux && <WindowControls />}
    </header>
  );
}

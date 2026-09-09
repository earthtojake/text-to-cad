import { Toaster } from '@emdash/ui/react/primitives';
import { LeftSidebar } from '@core/features/workbench/browser/sidebar/left-sidebar';
import { WindowScope } from '@core/features/workbench/browser/window-scope';
import {
  useWorkspaceSlots,
  useWorkspaceViewParams,
} from '@core/primitives/navigation/browser/navigation-hooks';
import { useTheme } from '@core/primitives/theme/browser';
import { BrowserShortcutForwarding, KeybindingDispatcherMount } from '@renderer/lib/keybindings';
import { WorkspaceContentLayout, WorkspaceLayout } from '@renderer/lib/layout/workspace-layout';

export function Workspace() {
  useTheme();
  const { WrapView, TitlebarSlot, MainPanel } = useWorkspaceSlots();
  const { params } = useWorkspaceViewParams();

  return (
    <WindowScope>
      <BrowserShortcutForwarding />
      <KeybindingDispatcherMount />
      <WrapView {...params}>
        <WorkspaceLayout
          leftSidebar={<LeftSidebar />}
          mainContent={
            <WorkspaceContentLayout titlebarSlot={<TitlebarSlot />} mainPanel={<MainPanel />} />
          }
        />
      </WrapView>
      <Toaster />
    </WindowScope>
  );
}

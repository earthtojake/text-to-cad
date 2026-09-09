import { FolderInput, Settings } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import React from 'react';
import { settingsViewDef } from '@core/features/settings/contributions/views';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import {
  isCurrentView,
  useNavigate,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';
import { cn } from '@core/primitives/styling/browser/cn';
import { SidebarHeaderActions } from './sidebar-header-actions';
import {
  SidebarContainer,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
} from './sidebar-primitives';
import { SidebarSearchTrigger } from './sidebar-search-trigger';
import { SidebarSpace } from './sidebar-space';
import { SidebarVirtualList } from './sidebar-virtual-list';
import { useSidebarDrop } from './use-sidebar-drop';

export const LeftSidebar: React.FC = observer(function LeftSidebar() {
  const { navigate } = useNavigate();
  const { currentView } = useWorkspaceSlots();

  const { isDragOver, onDragOver, onDragEnter, onDragLeave, onDrop } = useSidebarDrop();

  return (
    <div
      className={cn(
        // Closed = unmounted (store-driven conditional rendering), so the
        // border applies unconditionally.
        'surface-sunken relative flex h-full flex-col border-r border-border bg-(--em-surface) text-foreground-muted transition-colors',
        isDragOver && 'bg-background-info ring-2 ring-inset ring-border-info'
      )}
      onDragOver={onDragOver}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {isDragOver && (
        <div className="pointer-events-none absolute inset-0 z-50 flex flex-col items-center justify-center gap-2 bg-background-tertiary/80 backdrop-blur-sm">
          <FolderInput className="size-8 text-foreground" />
          <span className="text-xs font-medium text-foreground">Drop to add project</span>
        </div>
      )}
      <SidebarSpace />
      <SidebarContainer className="min-h-0 w-full flex-1 border-r-0">
        <SidebarContent className="flex flex-col">
          <SidebarGroup className="mb-0 flex min-h-0 flex-1 flex-col">
            <SidebarHeaderActions />
            <SidebarGroupContent className="flex min-h-0 flex-1 flex-col">
              <SidebarMenu className="flex min-h-0 flex-1 flex-col">
                <SidebarVirtualList />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <SidebarSearchTrigger />
            <SidebarMenuButton
              isActive={isCurrentView(currentView, 'settings')}
              onClick={() => navigate(settingsViewDef())}
              aria-label="Settings"
              className="w-full justify-between"
            >
              <span className="flex items-center gap-2">
                <Settings className="size-4" />
                Settings
              </span>
              <BoundShortcut command="app.settings" variant="keycaps" />
            </SidebarMenuButton>
          </SidebarMenu>
        </SidebarFooter>
      </SidebarContainer>
    </div>
  );
});

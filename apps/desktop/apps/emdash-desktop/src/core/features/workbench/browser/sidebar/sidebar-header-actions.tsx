import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { FolderPlus, SquarePen } from 'lucide-react';
import { AddProjectMenu } from '@core/features/projects/contributions/browser/add-project-menu';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { homeViewDef, newChatDraftView } from '@core/features/workbench/contributions/views';
import {
  useNavigate,
  useViewParams,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';

/**
 * Codex-style global navigation actions. Projects and their chats stay in the
 * list below; project files belong to the task's right-side panel.
 */
export function SidebarHeaderActions() {
  const { navigate } = useNavigate();
  const { currentView } = useWorkspaceSlots();
  const taskParams = useViewParams(taskViewDef);
  const projectParams = useViewParams(projectViewDef);
  const homeParams = useViewParams(homeViewDef);
  const currentProjectId =
    currentView === 'task'
      ? taskParams?.projectId
      : currentView === 'project'
        ? projectParams?.projectId
        : currentView === 'home'
          ? homeParams?.projectId
          : undefined;
  const startNewChat = () => navigate(newChatDraftView(currentProjectId));

  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-border px-3 py-2">
      <Button
        type="button"
        variant="ghost"
        size="base"
        className="min-w-0 flex-1 justify-start gap-2 px-2"
        onClick={startNewChat}
      >
        <SquarePen className="size-4 shrink-0" />
        <span className="truncate">New chat</span>
      </Button>
      <Tooltip.Root>
        <AddProjectMenu
          trigger={
            <Tooltip.Trigger
              render={
                <Button type="button" variant="ghost" size="base" icon aria-label="Add project">
                  <FolderPlus />
                </Button>
              }
            />
          }
        />
        <Tooltip.Content>Add project</Tooltip.Content>
      </Tooltip.Root>
    </div>
  );
}

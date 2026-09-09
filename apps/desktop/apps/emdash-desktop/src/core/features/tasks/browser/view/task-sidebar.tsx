import { observer } from 'mobx-react-lite';
import { SidebarConversationsList } from '@core/features/conversations/contributions/browser/sidebar-conversations-list';
import { EditorFileTree } from '@core/features/editor/contributions/browser/editor-file-tree';
import { ChangesPanel } from '@core/features/source-control/contributions/browser/changes-panel';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';

/**
 * Task sidebar body. Mounted only while the sidebar is expanded (the panel is
 * conditionally rendered in `ReadyTaskMainPanel`), so there is no
 * collapsed/hidden representation here.
 *
 * The active tab is store-driven conditional rendering, per the sync contract
 * (no display:none visibility in workbench surfaces), so switching tabs
 * remounts the previous body. Remount cost is modest by design: the
 * conversations list and file tree render from MobX stores (tree expansion
 * persists via the tasks.editor-tree memento) and lose only ephemeral
 * selection and scroll position; the changes panel's section sizes persist
 * via the shared layout storage (task panel-layouts memento) and survive the
 * remount. No tab body owns a Monaco instance.
 */
export const TaskSidebar = observer(function TaskSidebar() {
  const taskView = useTaskComposition();
  const activeTab = taskView.sidebarTab;

  return (
    <div className="h-full min-h-0 overflow-hidden">
      {activeTab === 'conversations' && <SidebarConversationsList />}
      {activeTab === 'changes' && <ChangesPanel />}
      {activeTab === 'files' && <EditorFileTree />}
    </div>
  );
});

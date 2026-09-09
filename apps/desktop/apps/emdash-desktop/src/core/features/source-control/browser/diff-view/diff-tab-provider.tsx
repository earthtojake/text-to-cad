import type { GitChangeStatus, GitObjectRef } from '@emdash/core/runtimes/git/api';
import { observer } from 'mobx-react-lite';
import { getDiffTabManagerStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import type { ActiveFile } from '@core/features/tasks/contributions/mementos';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import type {
  TabEntry,
  TabHandle,
  TabProvider,
  TabViewContext,
  TabContentProps,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { createTabProvider } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider-registry';
import { DiffTabBarItem, DiffTabBarItemDragPreview } from './diff-tab-item';
import { DiffView } from './main-panel/diff-view';
import type { DiffPayload } from './stores/diff-tab-resource';
import { DiffTabResource } from './stores/diff-tab-resource';

export interface DiffOpenArgs {
  activeFile: ActiveFile;
  status?: GitChangeStatus;
}

function refKey(ref: GitObjectRef): string {
  switch (ref.kind) {
    case 'branch':
      return `branch:${ref.branch.type === 'remote' ? `${ref.branch.remote.name}/${ref.branch.branch}` : ref.branch.branch}`;
    case 'commit':
      return `commit:${ref.sha}`;
    case 'tag':
      return `tag:${ref.name}`;
  }
}

function diffResourceKey(s: DiffPayload): string {
  const base = `${s.path}|${s.diffGroup}`;
  if (s.diffGroup === 'disk' || s.diffGroup === 'staged') return base;
  const origKey = refKey(s.originalRef);
  const modKey = s.modifiedRef ? refKey(s.modifiedRef) : '';
  return `${base}|${origKey}|${modKey}`;
}

function activeFileToDiffPayload(
  activeFile: ActiveFile,
  status: GitChangeStatus | undefined
): DiffPayload {
  return {
    path: activeFile.path,
    diffGroup: activeFile.group,
    originalRef: activeFile.originalRef,
    modifiedRef: activeFile.modifiedRef,
    prNumber: activeFile.prNumber,
    prBaseOid: activeFile.prBaseOid,
    prHeadOid: activeFile.prHeadOid,
    commitOriginalSha: activeFile.commitOriginalSha,
    commitModifiedSha: activeFile.commitModifiedSha,
    status,
  };
}

const DiffTabContent = observer(function DiffTabContent({ host }: TabContentProps) {
  const activeTab = host.resolvedTabs.find((t) => t.isActive);
  if (activeTab?.kind !== 'diff') return null;
  return <DiffView tab={activeTab.resource as DiffTabResource} />;
});

export const diffTabProvider: TabProvider<'diff', DiffPayload, DiffTabResource, DiffOpenArgs> =
  createTabProvider({
    kind: 'diff',
    mount: 'single',
    resourceKey: diffResourceKey,

    onBeforeOpen(args: DiffOpenArgs, _ctx: TabViewContext): DiffPayload | null {
      return activeFileToDiffPayload(args.activeFile, args.status);
    },

    initialize(
      entry: TabEntry<DiffPayload>,
      handle: TabHandle,
      ctx: TabViewContext
    ): DiffTabResource {
      const taskCtx = ctx as TaskTabContext;
      const manager = getDiffTabManagerStore(taskCtx.workspaceId);
      if (!manager) {
        throw new Error(`Diff tab manager unavailable for workspace ${taskCtx.workspaceId}`);
      }
      return new DiffTabResource(entry.tabId, entry.state, manager, handle);
    },

    dispose(_entry: TabEntry<DiffPayload>, resource: DiffTabResource): void {
      resource.dispose();
    },

    TabBarItem: DiffTabBarItem,
    TabBarItemDragPreview: DiffTabBarItemDragPreview,
    TabContent: DiffTabContent,
  });

export function diffGroupSuffix(diffGroup: DiffPayload['diffGroup']): string {
  switch (diffGroup) {
    case 'disk':
      return '(Working Tree)';
    case 'staged':
      return '(Index)';
    case 'pr':
      return '(PR)';
    case 'git':
      return '(Git)';
  }
}

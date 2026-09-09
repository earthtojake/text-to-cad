import { EmptyState } from '@emdash/ui/react/components';
import { Terminal } from 'lucide-react';
import { computed, makeObservable, reaction } from 'mobx';
import { observer } from 'mobx-react-lite';
import type { PtySession } from '@core/features/terminals/api/browser/pty/pty-session';
import { terminalRegistry } from '@core/features/terminals/api/browser/stores/terminal-registry';
import type {
  TerminalManagerStore,
  TerminalStore,
} from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import type {
  ResolvedTab,
  TabBarItemProps,
  TabContentProps,
  TabEntry,
  TabHandle,
  TabProvider,
  TabResource,
  TabViewContext,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { createTabProvider } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider-registry';
import {
  GenericTabDragPreview,
  GenericTabItem,
} from '@core/primitives/workbench-shell/browser/tabs/tab-bar/generic-tab-item';
import { TerminalPtyContent } from './terminal-pty-content';

export interface TerminalTabState {
  terminalId: string;
}

export interface TerminalTabOpenArgs {
  terminalId: string;
}

interface TerminalTabResourceView extends TabResource {
  readonly terminalId: string;
  readonly terminal: TerminalStore | undefined;
  readonly session: PtySession | null;
}

class TerminalTabResource implements TerminalTabResourceView {
  private readonly disposeStaleReaction: () => void;
  private isDisposed = false;

  constructor(
    readonly terminalId: string,
    private readonly terminalManager: TerminalManagerStore,
    private readonly handle: TabHandle
  ) {
    makeObservable(this, {
      terminal: computed,
    });

    this.disposeStaleReaction = reaction(
      () => ({
        isLoaded: this.terminalManager.isLoaded,
        hasTerminal: this.terminalManager.terminals.has(this.terminalId),
      }),
      ({ isLoaded, hasTerminal }) => {
        if (isLoaded && !hasTerminal) {
          setTimeout(() => void this.handle.close({ force: true }), 0);
        }
      },
      { fireImmediately: true }
    );
  }

  get terminal(): TerminalStore | undefined {
    return this.terminalManager.terminals.get(this.terminalId);
  }

  get session() {
    return this.terminalManager.sessions.get(this.terminalId) ?? null;
  }

  dispose(): void {
    if (this.isDisposed) return;
    this.isDisposed = true;
    this.disposeStaleReaction();
  }

  onActivateIntent(): void {
    if (this.terminalManager.hostAccess?.liveAction.kind === 'disabled') return;
    const session = this.session;
    if (session?.status === 'disconnected') void session.connect();
  }
}

class MissingTerminalTabResource implements TerminalTabResourceView {
  constructor(readonly terminalId: string) {}

  get terminal(): TerminalStore | undefined {
    return undefined;
  }

  get session() {
    return null;
  }

  dispose(): void {}

  onActivateIntent(): void {}
}

function TerminalIcon() {
  return <Terminal className="size-4 shrink-0" />;
}

const TerminalTabBarItem = observer(function TerminalTabBarItem({
  tab,
  host,
  ctx,
}: TabBarItemProps<TerminalTabResourceView>) {
  const terminal = tab.resource.terminal;
  const label = terminal?.data.name ?? 'Terminal';

  return (
    <GenericTabItem tab={tab} host={host} ctx={ctx} label={label} preSlot={<TerminalIcon />} />
  );
});

const TerminalTabBarItemDragPreview = observer(function TerminalTabBarItemDragPreview({
  tab,
}: {
  tab: ResolvedTab<TerminalTabResourceView>;
}) {
  const label = tab.resource.terminal?.data.name ?? 'Terminal';
  return <GenericTabDragPreview preSlot={<TerminalIcon />} label={label} />;
});

const TerminalTabContent = observer(function TerminalTabContent({ host, ctx }: TabContentProps) {
  const taskCtx = ctx as TaskTabContext;
  const terminalManager = terminalRegistry.get(taskCtx.taskId);
  const terminalTabs = host.resolvedTabs.filter(
    (tab): tab is ResolvedTab<TerminalTabResourceView> => tab.kind === 'terminal'
  );
  const activeTab = host.resolvedTabs.find((tab) => tab.isActive);
  const activeTerminal =
    activeTab?.kind === 'terminal' ? (activeTab.resource as TerminalTabResourceView) : null;
  const activeSession = activeTerminal?.session ?? null;
  const disabledReason = projectAvailabilityUi.getLiveActionDisabledReason(taskCtx.projectId);
  const allSessionIds = terminalTabs
    .map((tab) => tab.resource.session?.sessionId)
    .filter((id): id is string => Boolean(id));

  return (
    <TerminalPtyContent
      className="h-full"
      activeSession={activeSession}
      allSessionIds={allSessionIds}
      autoFocus={activeTerminal !== null && host.resolvedActiveTabId === activeTab?.tabId}
      emptyState={
        <EmptyState
          label={terminalManager?.isLoaded ? 'Terminal unavailable' : 'Loading terminal'}
          description={
            terminalManager?.isLoaded
              ? 'This terminal was removed from the drawer.'
              : 'Restoring terminal session.'
          }
        />
      }
      unavailableState={
        <EmptyState
          label="Terminal unavailable"
          description={disabledReason ?? 'Live actions are unavailable.'}
        />
      }
      disabledReason={disabledReason}
      remoteConnectionId={taskCtx.getRemoteConnectionId?.()}
      workspaceId={taskCtx.workspaceId}
    />
  );
});

export const terminalTabProvider: TabProvider<
  'terminal',
  TerminalTabState,
  TerminalTabResourceView,
  TerminalTabOpenArgs
> = createTabProvider({
  kind: 'terminal',
  mount: 'single',
  resourceKey: (state: TerminalTabState) => state.terminalId,

  onBeforeOpen(args: TerminalTabOpenArgs, ctx: TabViewContext): TerminalTabState | null {
    const taskCtx = ctx as TaskTabContext;
    const terminalManager = terminalRegistry.get(taskCtx.taskId);
    if (!terminalManager) return null;
    return { terminalId: args.terminalId };
  },

  initialize(
    entry: TabEntry<TerminalTabState>,
    handle: TabHandle,
    ctx: TabViewContext
  ): TerminalTabResourceView {
    const taskCtx = ctx as TaskTabContext;
    const terminalManager = terminalRegistry.get(taskCtx.taskId);
    if (!terminalManager) {
      setTimeout(() => void handle.close({ force: true }), 0);
      return new MissingTerminalTabResource(entry.state.terminalId);
    }
    return new TerminalTabResource(entry.state.terminalId, terminalManager, handle);
  },

  dispose(_entry: TabEntry<TerminalTabState>, resource: TerminalTabResourceView): void {
    resource.dispose();
  },

  TabBarItem: TerminalTabBarItem,
  TabBarItemDragPreview: TerminalTabBarItemDragPreview,
  TabContent: TerminalTabContent,
});

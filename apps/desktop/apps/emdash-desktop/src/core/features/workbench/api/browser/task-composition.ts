import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import type { TerminalShellId } from '@emdash/core/primitives/terminal-shell/api';
import { computed, makeAutoObservable, observable, reaction, runInAction, when } from 'mobx';
import { cadModelContextKey } from '@core/features/cad/api/browser/cad-agent';
import { cadModelCatalogMemento } from '@core/features/cad/contributions/mementos';
import type { ConversationManagerStore } from '@core/features/conversations/api/browser/conversation-manager';
import { EditorViewStore } from '@core/features/editor/api/browser/task-editor/stores/editor-view-store';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { getFilesClient } from '@core/features/files/api/browser/client';
import { DiffViewStore } from '@core/features/source-control/api/browser/diff-view/stores/diff-view-store';
import type { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import { PrStore } from '@core/features/source-control/api/browser/stores/pr-store';
import { getTaskPrAssociationStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import {
  diffTabManagerStoreToken,
  gitCheckoutStoreToken,
} from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import {
  taskChromeStore,
  type TaskChromeStore,
  type TaskFocusedRegion,
} from '@core/features/tasks/api/browser/stores/task-chrome-store';
import { TaskNavigationParticipant } from '@core/features/tasks/api/browser/stores/task-navigation-participant';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { type VisibleSidebarTab, visibleSidebarTab } from '@core/features/tasks/api/browser/types';
import {
  taskDiffPreferencesMemento,
  taskDiffSelectionMemento,
  taskEditorTreeMemento,
  taskPaneLayoutMemento,
  taskPanelLayoutsMemento,
  taskTerminalSelectionMemento,
  type TaskDiffPreferencesState,
  type TaskDiffSelectionState,
  type TaskPaneLayoutState,
  type TaskTerminalSelectionState,
  type TerminalDrawerActiveItem,
} from '@core/features/tasks/contributions/mementos';
import { taskSubject } from '@core/features/tasks/contributions/subject';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { computeSeededGridDimensions } from '@core/features/terminals/api/browser/pty/seeded-grid-dimensions';
import type { TerminalManagerStore } from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import { TerminalTabViewStore } from '@core/features/terminals/api/browser/task-terminal/terminal-tab-view-store';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import { taskTabView } from '@core/features/workbench/api/browser/task-tab-registry';
import {
  deleteSplitPaneLayoutEntries,
  resolvePaneLayoutFilePaths,
  sanitizeDiffSelection,
} from '@core/features/workbench/browser/task-composition-state';
import type { WorkspaceStore } from '@core/features/workspaces/api/browser/stores/workspace';
import { workspaceRegistry } from '@core/features/workspaces/api/browser/stores/workspace-registry';
import {
  relativeToWorkspace,
  resolveWorkspacePath,
} from '@core/features/workspaces/api/browser/workspace-path';
import { createChromeStore } from '@core/primitives/chrome-stores/browser';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { log } from '@core/primitives/logging/browser/logger';
import {
  createLayoutStorage,
  sanitizedMemento,
  type MementoHandle,
  type SubjectSpace,
} from '@core/primitives/mementos/browser';
import { getMementoClient } from '@core/primitives/mementos/browser';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import { focusTracker } from '@core/primitives/telemetry/browser/focus-tracker';
import {
  planCanonicalCadCatalogTabRetargets,
  planCanonicalCadRestore,
  planLegacyCadRestore,
  type CanonicalCadRestorePlan,
} from './canonical-cad-restore';

export type RendererKind =
  | 'monaco'
  | 'markdown'
  | 'diff'
  | 'agents'
  | 'browser'
  | 'terminal'
  | 'other-file';

/**
 * Workbench-owned composition boundary for a task view.
 *
 * Task identity is joined to workspace-scoped stores only here. Feature state is
 * resolved through scoped-store tokens and task-tab providers rather than being
 * attached to TaskStore.
 */
export class TaskComposition {
  readonly space: SubjectSpace<'task'>;
  /** Task chrome command store — the only mutation path for chrome facts. */
  readonly chrome: TaskChromeStore;
  readonly paneLayout: ReturnType<typeof taskTabView.createPaneLayoutStore>;
  readonly terminalTabs: TerminalTabViewStore;
  readonly editorView: EditorViewStore;

  get activePane(): ReturnType<typeof taskTabView.createPaneLayoutStore>['focusedPane'] {
    return this.paneLayout.focusedPane;
  }

  diffView: DiffViewStore | null = null;
  prStore: PrStore | null = null;

  private readonly _disposers: (() => void)[] = [];
  private _sessionDisposers: (() => void)[] = [];
  private _workspace: WorkspaceStore | null = null;
  private _acquiredWorkspaceId: string | null = null;
  private _activated = false;
  private _isCreatingTerminal = false;
  private _paneHydrated = false;
  private _initializing = false;

  private readonly _terminalSelectionHandle: MementoHandle<TaskTerminalSelectionState>;
  private readonly _diffPreferencesHandle: MementoHandle<TaskDiffPreferencesState>;
  private readonly _diffSelectionHandle: MementoHandle<TaskDiffSelectionState>;

  constructor(
    readonly projectId: string,
    readonly taskId: string,
    readonly workspaceId: string,
    private readonly _taskStore: TaskStore,
    private readonly _terminals: TerminalManagerStore,
    private readonly _conversations: ConversationManagerStore,
    private readonly _gitRepository: GitRepositoryStore
  ) {
    this.space = getMementoClient().subject(taskSubject({ taskId }));
    this.chrome = createChromeStore(taskChromeStore, this.space);
    this._terminalSelectionHandle = sanitizedMemento(
      this.space.handle(taskTerminalSelectionMemento),
      {
        deps: () =>
          this._terminals.isLoaded ? new Set(this._terminals.terminals.keys()) : undefined,
        sanitize: sanitizeTerminalSelection,
      }
    );
    this._diffPreferencesHandle = this.space.handle(taskDiffPreferencesMemento);
    this._diffSelectionHandle = this.space.handle(taskDiffSelectionMemento);

    const taskRef = taskViewDef({ projectId, taskId });
    const getWorkspacePath = () => this._workspace?.path;
    const paneLayoutMemento = sanitizedMemento(
      sanitizedMemento(this.space.handle(taskPaneLayoutMemento), {
        deps: () =>
          this._conversations.list.data
            ? new Set(this._conversations.conversations.keys())
            : undefined,
        sanitize: sanitizePaneLayoutConversations,
      }),
      {
        deps: getWorkspacePath,
        sanitize: resolvePaneLayoutFilePaths,
      }
    );
    const taskCtx: TaskTabContext = {
      viewId: taskId,
      projectId,
      workspaceId,
      taskId,
      get workspacePath(): string | undefined {
        return getWorkspacePath();
      },
      getRemoteConnectionId: () => this._workspace?.sshConnectionId,
    };
    // Split-pane sizes live on the shared panel-layouts storage (spec:
    // pane-layout ownership); when a pane group is destroyed its persisted
    // entries are dropped so a later re-split starts fresh from defaults.
    const panelLayoutsHandle = this.space.handle(taskPanelLayoutsMemento);
    const panelLayoutsStorage = createLayoutStorage(this.space, taskPanelLayoutsMemento);
    this.paneLayout = taskTabView.createPaneLayoutStore(taskCtx, {
      snapshotMemento: paneLayoutMemento,
      onActiveTabChange: (tabId) => {
        if (tabId) getNavigation().reportLocation(taskRef, { tabId });
      },
      onPaneDestroyed: (paneId) => {
        deleteSplitPaneLayoutEntries(
          panelLayoutsStorage,
          Object.keys(panelLayoutsHandle.value.layouts),
          paneId
        );
      },
    });
    this._disposers.push(
      getNavigation().attachParticipant(taskRef, new TaskNavigationParticipant(this.paneLayout))
    );
    // Feed measured pane dimensions to conversation PTY spawns so the first
    // spawn starts at the pane's real size instead of the backend default.
    this._conversations.setInitialSizeResolver((conversationId) =>
      resolveConversationInitialSize(this.paneLayout, conversationId)
    );
    this.terminalTabs = new TerminalTabViewStore(
      this._terminalSelectionHandle,
      () => this._terminals
    );
    this.editorView = new EditorViewStore(
      this.paneLayout,
      taskId,
      workspaceId,
      this.space.handle(taskEditorTreeMemento),
      this._terminals.hostAccess
    );

    makeAutoObservable<
      TaskComposition,
      '_diffPreferencesHandle' | '_diffSelectionHandle' | '_terminalSelectionHandle'
    >(this, {
      paneLayout: false,
      terminalTabs: false,
      editorView: false,
      diffView: observable.ref,
      activeRenderer: computed,
      space: false,
      chrome: false,
      _terminalSelectionHandle: false,
      _diffPreferencesHandle: false,
      _diffSelectionHandle: false,
    });

    this._disposers.push(
      reaction(
        () =>
          getNavigation().currentRef.viewId === 'task' &&
          (getNavigation().currentRef.params as { taskId?: string }).taskId === taskId,
        (isActive) => this.paneLayout.setViewActive(isActive),
        { fireImmediately: true }
      ),
      reaction(
        () => ({
          state: this._taskStore.state,
          workspaceId: this._taskStore.workspaceId,
          path: this._taskStore.workspacePath,
          sshConnectionId: this._taskStore.workspaceSshConnectionId,
        }),
        () => this.syncWorkspace(),
        { fireImmediately: true }
      ),
      // focusedRegion is mutated only inside chrome commands; the analytics
      // transition observes the ephemeral field so every path is reported.
      reaction(
        () => this.chrome.ephemeral.focusedRegion,
        (region) => focusTracker.transition({ focusedRegion: region }, 'region_switch')
      )
    );
  }

  get sidebarTab(): VisibleSidebarTab {
    return visibleSidebarTab(this.chrome.state.sidebarTab);
  }

  get isSidebarCollapsed(): boolean {
    return this.chrome.state.sidebarCollapsed;
  }

  get isTerminalDrawerOpen(): boolean {
    return this.chrome.state.terminalDrawerOpen;
  }

  get focusedRegion(): TaskFocusedRegion {
    return this.chrome.ephemeral.focusedRegion;
  }

  get terminalDrawerActiveItem(): TerminalDrawerActiveItem | undefined {
    return this._terminalSelectionHandle.value.activeItem;
  }

  get activeRenderer(): RendererKind {
    const desc = this.activePane.activeEntry;
    if (desc?.kind === 'diff') return 'diff';
    if (desc?.kind === 'browser') return 'browser';
    if (desc?.kind === 'terminal') return 'terminal';
    const resource = this.activePane.activeResourceOfKind<FileTabResource>('file');
    if (!resource) return 'agents';
    if (resource.fileKind === 'markdown' && resource.viewMode === 'preview') return 'markdown';
    if (resource.fileKind === 'text' || resource.viewMode === 'source') return 'monaco';
    return 'other-file';
  }

  get workspace(): WorkspaceStore | null {
    return this._workspace;
  }

  private async hydrateAndSeedPaneLayout(): Promise<void> {
    if (this._paneHydrated) return;
    await this._conversations.list.load();
    // Persisted pane state must be loaded before hydrate() reads it; the
    // conversations-list await above is not a reliable ordering guarantee.
    // hydrate() also awaits the memento's own ready internally, so restore
    // can never silently skip on slow hydration.
    await this.space.ready;
    await this.paneLayout.hydrate();
    this._paneHydrated = true;

    const conversations = [...this._conversations.conversations].map(([, store]) => store.data);
    const cadCatalog = this.space.handle(cadModelCatalogMemento).value;
    const restorePlan =
      planCanonicalCadRestore(cadCatalog, conversations) ??
      (await this.resolveLegacyCadRestore(conversations));
    const hasChatTab = this.paneLayout.groups.some(({ pane }) =>
      pane.resolvedTabs.some((tab) => tab.kind === 'acp-chat' || tab.kind === 'conversation')
    );
    let cadGroup = this.paneLayout.groups.find(({ pane }) =>
      pane.resolvedTabs.some((tab) => tab.kind === 'cad')
    );

    if (!hasChatTab) {
      const selectedConversation =
        (restorePlan?.conversationId
          ? this._conversations.conversations.get(restorePlan.conversationId)
          : undefined) ??
        [...this._conversations.conversations.values()].find(
          (store) => store.isInitialConversation
        ) ??
        // Older Hardcore tasks stored their Design chat as a model conversation
        // rather than the task's initial chat. Reuse that real conversation when
        // restoring a CAD artifact so history is preserved in the flat shell.
        (cadGroup && !restorePlan
          ? this._conversations.conversations.values().next().value
          : undefined);

      if (selectedConversation) {
        if (cadGroup) this.paneLayout.setActiveGroup(cadGroup.paneId);
        runInAction(() => {
          const config = {
            preview: false,
            target: cadGroup ? ('left' as const) : ('active' as const),
          };
          if (selectedConversation.data.type === 'acp') {
            this.paneLayout.open(
              'acp-chat',
              { conversationId: selectedConversation.data.id },
              config
            );
          } else {
            this.paneLayout.open(
              'conversation',
              { conversationId: selectedConversation.data.id },
              config
            );
          }
        });
      }
    }

    cadGroup = this.paneLayout.groups.find(({ pane }) =>
      pane.resolvedTabs.some((tab) => tab.kind === 'cad')
    );
    if (this._workspace) {
      const workspacePath = this._workspace.path;
      const retargetCandidates = this.paneLayout.groups.flatMap((group) =>
        planCanonicalCadCatalogTabRetargets(
          cadCatalog,
          group.pane.resolvedTabs.flatMap((tab) => {
            if (tab.kind !== 'cad' || !('path' in tab.resource)) return [];
            const path = (tab.resource as { path?: unknown }).path;
            if (typeof path !== 'string') return [];
            const relativePath = relativeToWorkspace(workspacePath, path);
            return [
              {
                tabId: tab.tabId,
                path: relativePath,
                contextKey: cadModelContextKey(relativePath),
              },
            ];
          })
        ).map((plan) => ({ group, plan }))
      );
      for (const { group, plan } of retargetCandidates) {
        const previousActiveTabId = group.pane.activeTabId;
        const staleTab = group.pane.resolvedTabs.find((tab) => tab.tabId === plan.tabId);
        runInAction(() => {
          group.pane.closeTab(plan.tabId);
          group.pane.open(
            'cad',
            { path: resolveWorkspacePath(workspacePath, plan.path) },
            {
              preview: staleTab?.isPreview ?? false,
              target: { paneId: group.paneId },
            }
          );
          if (previousActiveTabId && previousActiveTabId !== plan.tabId) {
            group.pane.setActiveTab(previousActiveTabId);
          }
        });
      }
    }
    if (cadGroup || !restorePlan || !this._workspace) return;

    const artifactGroup = this.paneLayout.groups.find(({ pane }) =>
      pane.resolvedTabs.some((tab) => tab.kind === 'file')
    );
    const chatGroup = this.paneLayout.groups.find(({ pane }) =>
      pane.resolvedTabs.some((tab) => tab.kind === 'acp-chat' || tab.kind === 'conversation')
    );
    if (chatGroup && !artifactGroup) this.paneLayout.setActiveGroup(chatGroup.paneId);
    runInAction(() => {
      this.paneLayout.open(
        'cad',
        { path: resolveWorkspacePath(this._workspace?.path, restorePlan.path) },
        {
          preview: false,
          target: artifactGroup ? { paneId: artifactGroup.paneId } : chatGroup ? 'right' : 'active',
        }
      );
    });
  }

  private async resolveLegacyCadRestore(
    conversations: Parameters<typeof planLegacyCadRestore>[0]
  ): Promise<CanonicalCadRestorePlan | null> {
    const workspace = this._workspace;
    const legacyPlan = planLegacyCadRestore(conversations);
    if (!workspace || !legacyPlan) return null;

    try {
      const files = await getFilesClient();
      const candidates = await Promise.all(
        legacyPlan.candidatePaths.map(async (path) => {
          const absolutePath = resolveWorkspacePath(workspace.path, path);
          const uri = encodeResourceUri(
            hostFileRefFromNativePath(absolutePath, workspace.sshConnectionId)
          );
          const result = await files.fs.exists({ uri });
          return result.success && result.data.exists ? path : null;
        })
      );
      const path = candidates.find((candidate): candidate is string => candidate !== null);
      return path
        ? {
            contextKey: legacyPlan.contextKey,
            conversationId: legacyPlan.conversationId,
            path,
          }
        : null;
    } catch (error) {
      log.warn('Could not recover a legacy CAD artifact:', error);
      return null;
    }
  }

  activate(): void {
    this._activated = true;
    if (this._acquiredWorkspaceId) workspaceRegistry.activate(this._acquiredWorkspaceId);
  }

  private syncWorkspace(): void {
    const {
      workspaceId,
      workspacePath: path,
      workspaceSshConnectionId: sshConnectionId,
    } = this._taskStore;
    if (this._taskStore.state !== 'provisioned' || workspaceId !== this.workspaceId || !path) {
      this.suspend();
      this.releaseWorkspace();
      return;
    }
    if (
      this._acquiredWorkspaceId === workspaceId &&
      this._workspace?.path === path &&
      this._workspace.sshConnectionId === sshConnectionId
    ) {
      return;
    }

    this.suspend();
    this.releaseWorkspace();
    this._workspace = workspaceRegistry.acquire({
      projectId: this.projectId,
      workspaceId,
      path,
      gitRepository: this._gitRepository,
      sshConnectionId,
    });
    this._acquiredWorkspaceId = workspaceId;
    if (this._activated) workspaceRegistry.activate(workspaceId);
    this.initialize();
  }

  private releaseWorkspace(): void {
    if (this._acquiredWorkspaceId) {
      workspaceRegistry.release(this._acquiredWorkspaceId, this._workspace ?? undefined);
    }
    this._acquiredWorkspaceId = null;
    this._workspace = null;
  }

  private initialize(): void {
    if (this.prStore || this._initializing || !this._workspace || !this._acquiredWorkspaceId) {
      return;
    }
    const workspace = this._workspace;
    const workspaceId = this._acquiredWorkspaceId;
    this._initializing = true;
    void this.initializeReadyWorkspace(workspace, workspaceId);
  }

  private async initializeReadyWorkspace(
    workspace: WorkspaceStore,
    workspaceId: string
  ): Promise<void> {
    try {
      await this.hydrateAndSeedPaneLayout();
    } catch (error) {
      log.error('Failed to hydrate task pane layout:', error);
    }
    if (this._workspace !== workspace || this._acquiredWorkspaceId !== workspaceId) {
      this._initializing = false;
      return;
    }
    const gitCheckout = workspace.get(gitCheckoutStoreToken);
    this.prStore = new PrStore(
      this.projectId,
      workspaceId,
      this._gitRepository,
      gitCheckout,
      getTaskPrAssociationStore(this._taskStore)
    );

    const diffSelectionHandle = sanitizedMemento(this._diffSelectionHandle, {
      deps: () =>
        gitCheckout.hasData
          ? new Set([
              ...gitCheckout.unstagedFileChanges.map((file) => file.path),
              ...gitCheckout.stagedFileChanges.map((file) => file.path),
            ])
          : undefined,
      sanitize: sanitizeDiffSelection,
    });
    this.diffView = new DiffViewStore(
      gitCheckout,
      this.prStore,
      this._diffPreferencesHandle,
      diffSelectionHandle
    );
    workspace.get(diffTabManagerStoreToken).bindSession({
      gitCheckout,
      pr: this.prStore,
      diffView: this.diffView,
    });

    this.paneLayout.startPersistence();
    this._sessionDisposers.push(
      reaction(
        () => ({
          isDrawerOpen: this.isTerminalDrawerOpen,
          isCreatingTerminal: this._isCreatingTerminal,
          isLoaded: this._terminals.isLoaded,
          terminalCount: this._terminals.terminals.size,
        }),
        (state, previous) => {
          if (
            state.isDrawerOpen &&
            !state.isCreatingTerminal &&
            state.isLoaded &&
            state.terminalCount === 0 &&
            (previous === undefined || previous.terminalCount > 0 || !previous.isLoaded)
          ) {
            runInAction(() => {
              this.chrome.commands.closeTerminalDrawer();
              this._terminalSelectionHandle.update((current) => ({
                ...current,
                activeItem: undefined,
              }));
            });
          }
        },
        { fireImmediately: true }
      )
    );

    this.editorView.startFiles(workspace.path, workspace.sshConnectionId);
    this._sessionDisposers.push(
      reaction(
        () => {
          const files = this.editorView.files;
          if (!files) return '';
          const expanded = [...this.editorView.expandedPaths].sort().join('\0');
          const loaded = [...files.loadedPaths].sort().join('\0');
          const pending = [...files.pendingPaths].sort().join('\0');
          return `${expanded}::${loaded}::${pending}::${files.nodes.size}`;
        },
        () => {
          const files = this.editorView.files;
          if (files) files.reconcileVisibleScopes(this.editorView.expandedPaths);
        },
        { fireImmediately: true }
      )
    );
    this._initializing = false;
  }

  suspend(): void {
    this.diffView?.dispose();
    this.diffView = null;
    this._workspace?.get(diffTabManagerStoreToken).unbindSession();
    this.prStore?.dispose();
    this.prStore = null;
    this.paneLayout.stopPersistence();
    for (const dispose of this._sessionDisposers) dispose();
    this._sessionDisposers = [];
    this.editorView.disposeFiles();
  }

  dispose(): void {
    this._conversations.setInitialSizeResolver(null);
    this.suspend();
    this.releaseWorkspace();
    for (const dispose of this._disposers) dispose();
    this.paneLayout.dispose();
    this.terminalTabs.dispose();
    this.editorView.dispose();
    void this.space.release().catch((error: unknown) => getMementoClient().reportError(error));
  }

  activateLastTabOfKind(kind: 'conversation' | 'file' | 'diff' | 'browser' | 'terminal'): void {
    const tabId = [...this.activePane.tabOrder]
      .reverse()
      .find((id) => this.activePane.entries.get(id)?.kind === kind);
    if (!tabId) return;
    const panelView =
      kind === 'conversation'
        ? 'agents'
        : kind === 'file'
          ? 'editor'
          : kind === 'diff'
            ? 'diff'
            : kind === 'browser'
              ? 'browser'
              : 'terminal';
    focusTracker.transition({ mainPanel: panelView }, 'panel_switch');
    this.activePane.setActiveTab(tabId);
  }

  revealWorkspaceFile(path: string): void {
    this.chrome.commands.openSidebarTab('files');
    this.editorView.requestRevealFile(path);
  }

  setFocusedRegion(region: TaskFocusedRegion): void {
    this.chrome.commands.focusRegion(region);
  }

  setTerminalDrawerActiveItem(item: TerminalDrawerActiveItem): void {
    this._terminalSelectionHandle.update((current) => ({ ...current, activeItem: item }));
  }

  async openNewTerminal(shell?: TerminalShellId): Promise<string | undefined> {
    this.chrome.commands.openTerminalDrawer();
    const terminalId = await this.createDefaultTerminal(shell);
    if (!terminalId) return undefined;
    runInAction(() => {
      this.terminalTabs.setActiveTab(terminalId);
      this.setTerminalDrawerActiveItem({ kind: 'terminal', id: terminalId });
    });
    return terminalId;
  }

  private async createDefaultTerminal(shell?: TerminalShellId): Promise<string | undefined> {
    if (this._isCreatingTerminal) return undefined;
    this._isCreatingTerminal = true;
    try {
      return (await this._terminals.createDefaultTerminal(shell))?.id;
    } catch (error) {
      log.error('Failed to create terminal:', error);
      return undefined;
    } finally {
      runInAction(() => {
        this._isCreatingTerminal = false;
      });
    }
  }
}

const INITIAL_SIZE_MEASUREMENT_TIMEOUT_MS = 150;

/**
 * Waits briefly for the pane hosting the conversation tab (or the focused
 * pane) to report its first pixel measurement, then converts it to cols/rows
 * so the PTY can spawn at the pane's real size. Resolves null — leaving the
 * spawn on the backend's default size — when no measurement lands in time.
 */
async function resolveConversationInitialSize(
  paneLayout: TaskComposition['paneLayout'],
  conversationId?: string
): Promise<{ cols: number; rows: number } | null> {
  // Yield one microtask: hydrate fires from inside the tab's initialize(),
  // before the entry is registered on its pane, so an immediate scan would
  // miss the tab and fall back to the focused pane.
  await Promise.resolve();
  const pane =
    (conversationId
      ? paneLayout.groups.find((group) => group.pane.hasOpenKey('conversation', conversationId))
          ?.pane
      : undefined) ?? paneLayout.focusedPane;
  try {
    await when(() => pane.dimensions !== null, { timeout: INITIAL_SIZE_MEASUREMENT_TIMEOUT_MS });
  } catch {
    return null;
  }
  const dimensions = pane.dimensions;
  if (!dimensions) return null;
  return computeSeededGridDimensions(dimensions.width, dimensions.height);
}

function sanitizeTerminalSelection(
  value: TaskTerminalSelectionState,
  terminalIds: ReadonlySet<string>
): TaskTerminalSelectionState {
  const tabOrder = value.tabOrder.filter((id) => terminalIds.has(id));
  const activeTabId =
    value.activeTabId && terminalIds.has(value.activeTabId) ? value.activeTabId : tabOrder[0];
  const activeItem =
    value.activeItem?.kind === 'terminal' && !terminalIds.has(value.activeItem.id)
      ? undefined
      : value.activeItem;
  return { ...value, tabOrder, activeTabId, activeItem };
}

function sanitizePaneLayoutConversations(
  value: TaskPaneLayoutState,
  conversationIds: ReadonlySet<string>
): TaskPaneLayoutState {
  const groups = value.groups.map((group) => {
    const tabs = group.tabManager.tabs.filter(
      (tab) =>
        (tab.kind !== 'conversation' && tab.kind !== 'acp-chat') ||
        conversationIds.has(tab.conversationId)
    );
    const activeTabId =
      group.tabManager.activeTabId && tabs.some((tab) => tab.tabId === group.tabManager.activeTabId)
        ? group.tabManager.activeTabId
        : tabs[0]?.tabId;
    return {
      ...group,
      tabManager: {
        ...group.tabManager,
        tabs,
        activeTabId,
      },
    };
  });
  const activeGroupId = groups.some((group) => group.groupId === value.activeGroupId)
    ? value.activeGroupId
    : groups[0]?.groupId;
  return {
    ...value,
    groups,
    activeGroupId: activeGroupId ?? value.activeGroupId,
  };
}

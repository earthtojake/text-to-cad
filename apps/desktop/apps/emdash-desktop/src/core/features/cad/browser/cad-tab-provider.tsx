import { Button, toast } from '@emdash/ui/react/primitives';
import { Box, Loader2, RotateCcw } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useRef } from 'react';
import { BrowserPane } from '@core/features/browser/api/browser/browser-pane';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import type { BrowserState } from '@core/features/browser/api/browser/browser-tab-state';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import { cadModelContextKey } from '@core/features/cad/api/browser/cad-agent';
import {
  availableEngineeringWorkspaceModes,
  type EngineeringWorkspaceMode,
} from '@core/features/cad/api/browser/cad-engineering-object';
import { CadTabResource } from '@core/features/cad/api/browser/cad-tab-resource';
import {
  ensureCadModel,
  reconcileCadArtifactFromDisk,
  type CadModelIdentity,
} from '@core/features/cad/api/cad-model-state';
import { CAD_VALIDATION_WIRE_TIMEOUT_MS } from '@core/features/cad/api/cad-validation';
import { cadModelCatalogMemento } from '@core/features/cad/contributions/mementos';
import { getAppSettingValueSnapshot } from '@core/features/settings/api/browser/app-settings-client';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';
import {
  relativeToWorkspace,
  resolveWorkspacePath,
} from '@core/features/workspaces/api/browser/workspace-path';
import { normalizeBrowserProfileSelection } from '@core/primitives/browser/api';
import { useMemento } from '@core/primitives/mementos/react/use-memento';
import type {
  ResolvedTab,
  TabBarItemProps,
  TabContentProps,
  TabEntry,
  TabHandle,
  TabProvider,
  TabViewContext,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { createTabProvider } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider-registry';
import {
  GenericTabDragPreview,
  GenericTabItem,
} from '@core/primitives/workbench-shell/browser/tabs/tab-bar/generic-tab-item';
import { cadOutputPath } from './cad-design-history-model';
import { CadDrawingPanel } from './cad-drawing-panel';
import { cadModelSourcePath, selectCadModelFiles } from './cad-model-files-model';
import { CadSourcePanel } from './cad-source-panel';
import { CadWorkbenchChatRelay } from './cad-workbench-chat-relay';
import { CadWorkspaceModeBar } from './cad-workspace-mode-bar';

export interface CadState extends BrowserState {
  path: string;
  workspacePath: string;
  chatOpen?: boolean;
  workspaceMode?: EngineeringWorkspaceMode;
}

export interface CadOpenArgs {
  path: string;
}

const CadTabContent = observer(function CadTabContent({ host, ctx }: TabContentProps) {
  const taskView = useTaskComposition();
  const [catalog] = useMemento(cadModelCatalogMemento);
  const cadTabs = host.resolvedTabs.filter(
    (tab): tab is ResolvedTab<CadTabResource> => tab.kind === 'cad'
  );
  const activeCadTab = cadTabs.find((tab) => tab.isActive);
  const hasWorkbenchChat = taskView.paneLayout.groups.some(({ pane }) =>
    pane.resolvedTabs.some((tab) => tab.kind === 'acp-chat' || tab.kind === 'conversation')
  );
  const fileCandidates = taskView.editorView.files
    ? [...taskView.editorView.files.nodes.values()]
    : [];
  const knownSourcePath = (resource: CadTabResource): string | null => {
    const modelPath = cadOutputPath(relativeToWorkspace(resource.workspacePath, resource.path));
    const sourcePath = catalog.models[cadModelContextKey(modelPath)]?.sourcePath;
    return sourcePath ? resolveWorkspacePath(resource.workspacePath, sourcePath) : null;
  };

  return (
    <>
      {cadTabs.map((tab) => {
        const resource = tab.resource;
        const visible = activeCadTab?.tabId === tab.tabId;
        const modelFiles = selectCadModelFiles(fileCandidates, resource.path);
        const sourcePath = cadModelSourcePath(
          fileCandidates,
          resource.path,
          knownSourcePath(resource)
        );
        const drawingFiles = modelFiles.filter((file) => file.role === 'drawing');
        const modes = availableEngineeringWorkspaceModes({
          kind: 'part',
          implementedModes: ['3d', 'source'],
          hasSource: Boolean(sourcePath),
          createdModes: drawingFiles.length > 0 ? ['drawing'] : [],
        });
        const activeMode = modes.includes(resource.workspaceMode) ? resource.workspaceMode : '3d';
        const changeMode = (mode: EngineeringWorkspaceMode) => {
          resource.setWorkspaceMode(mode);
        };
        const addOutput = (mode: 'drawing') => {
          if (mode !== 'drawing' || resource.drawingCreating) return;
          resource.setDrawingCreating(true);
          toast.info('Creating an engineering drawing from the current model revision…');
          void (async () => {
            const result = await (
              await getBrowserClient()
            ).createCadDrawing(
              {
                workspacePath: resource.workspacePath,
                filePath: resource.path,
              },
              { timeoutMs: 180_000 }
            );
            if (!result.success) {
              toast.error(result.error);
              return;
            }
            await taskView.editorView.files?.refresh();
            resource.setWorkspaceMode('drawing');
            toast.success('Engineering drawing created', {
              description: `Linked to revision ${result.revisionId.replace('sha256:', '').slice(0, 12)}.`,
            });
          })()
            .catch((error) => {
              toast.error(error instanceof Error ? error.message : String(error));
            })
            .finally(() => resource.setDrawingCreating(false));
        };
        return (
          <div
            key={tab.tabId}
            className="absolute inset-0 flex min-h-0 flex-col bg-background"
            style={{ display: visible ? 'flex' : 'none' }}
            inert={visible ? undefined : true}
          >
            {visible ? (
              <CadArtifactReconciliationBridge resource={resource} sourcePath={sourcePath} />
            ) : null}
            {visible && hasWorkbenchChat ? (
              <CadWorkbenchChatRelay
                resource={resource}
                task={ctx as TaskTabContext}
                sourcePath={sourcePath}
              />
            ) : null}
            <div className="flex min-h-0 flex-1">
              <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                <CadWorkspaceModeBar
                  modes={modes}
                  activeMode={activeMode}
                  onChange={changeMode}
                  onRefresh={resource.refreshViewer}
                  onCapture={resource.requestCaptureForChat}
                  onAddOutput={addOutput}
                  creatingOutput={resource.drawingCreating ? 'drawing' : null}
                />
                <div className="relative min-h-0 flex-1 overflow-hidden">
                  <div
                    className="absolute inset-0 bg-background-secondary"
                    style={{ display: activeMode === '3d' ? 'block' : 'none' }}
                    inert={activeMode === '3d' ? undefined : true}
                  >
                    {resource.status === 'ready' ? (
                      <BrowserPane
                        browserId={resource.browserId}
                        visible={visible && activeMode === '3d'}
                        showToolbar={false}
                      />
                    ) : resource.status === 'error' ? (
                      <CadError resource={resource} />
                    ) : (
                      <div className="flex h-full items-center justify-center gap-2 text-sm text-foreground-muted">
                        <Loader2 className="size-4 animate-spin" />
                        Starting local CAD engine…
                      </div>
                    )}
                  </div>
                  {visible && activeMode === 'source' && sourcePath ? (
                    <div className="absolute inset-0">
                      <CadSourcePanel
                        resource={resource}
                        task={ctx as TaskTabContext}
                        sourcePath={sourcePath}
                      />
                    </div>
                  ) : null}
                  {visible && activeMode === 'drawing' ? (
                    <div className="absolute inset-0">
                      <CadDrawingPanel
                        drawings={drawingFiles}
                        regenerating={resource.drawingCreating}
                        onRegenerate={() => addOutput('drawing')}
                      />
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
});

function CadArtifactReconciliationBridge({
  resource,
  sourcePath,
}: {
  resource: CadTabResource;
  sourcePath: string | null;
}) {
  const [catalog, setCatalog] = useMemento(cadModelCatalogMemento);
  const openedPath = relativeToWorkspace(resource.workspacePath, resource.path);
  const modelPath = cadOutputPath(openedPath);
  const linkedSourcePath = sourcePath
    ? relativeToWorkspace(resource.workspacePath, sourcePath)
    : undefined;
  const contextKey = cadModelContextKey(modelPath);
  const identity = useMemo<CadModelIdentity>(
    () => ({
      contextKey,
      modelPath,
      ...(linkedSourcePath ? { sourcePath: linkedSourcePath } : {}),
    }),
    [contextKey, linkedSourcePath, modelPath]
  );
  const runStatus = catalog.models[contextKey]?.run.status;
  const attemptedPathRef = useRef<string | null>(null);

  useEffect(() => {
    setCatalog((current) => ensureCadModel(current, identity, new Date().toISOString()));
  }, [identity, setCatalog]);

  useEffect(() => {
    if (runStatus === 'generating' || runStatus === 'validating') return;
    const attemptKey = `${resource.workspacePath}\0${resource.path}`;
    if (attemptedPathRef.current === attemptKey) return;
    attemptedPathRef.current = attemptKey;
    let cancelled = false;
    void (async () => {
      const result = await (
        await getBrowserClient()
      ).validateCadModel(
        { workspacePath: resource.workspacePath, filePath: resource.path },
        { timeoutMs: CAD_VALIDATION_WIRE_TIMEOUT_MS }
      );
      if (cancelled || !result.success) return;
      const checkedAt = new Date().toISOString();
      setCatalog((current) => {
        const ensured = ensureCadModel(current, identity, checkedAt);
        return reconcileCadArtifactFromDisk(
          ensured,
          contextKey,
          result.artifact,
          result.facts,
          checkedAt
        );
      });
      resource.refreshViewer();
    })().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [contextKey, identity, resource, runStatus, setCatalog]);

  return null;
}

function CadError({ resource }: { resource: CadTabResource }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="flex max-w-md flex-col items-center gap-3 text-center">
        <Box className="size-8 text-foreground-muted" />
        <div>
          <h1 className="text-sm font-medium text-foreground">Couldn’t start Hardcore CAD</h1>
          <p className="mt-1 text-sm text-foreground-muted">{resource.error}</p>
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={resource.retry}>
          <RotateCcw className="mr-1 size-3" />
          Retry
        </Button>
      </div>
    </div>
  );
}

const CadTabBarItem = observer(function CadTabBarItem({
  tab,
  host,
  ctx,
}: TabBarItemProps<CadTabResource>) {
  return (
    <GenericTabItem
      tab={tab}
      host={host}
      ctx={ctx}
      label={fileName(tab.resource.path)}
      preSlot={
        <span className="shrink-0 text-foreground-muted [&>svg]:size-3">
          {tab.resource.status === 'starting' ? <Loader2 className="animate-spin" /> : <Box />}
        </span>
      }
      hasError={tab.resource.status === 'error'}
    />
  );
});

function CadTabBarItemDragPreview({ tab }: { tab: ResolvedTab<CadTabResource> }) {
  return (
    <GenericTabDragPreview
      preSlot={<Box className="size-3 shrink-0 text-foreground-muted" />}
      label={fileName(tab.resource.path)}
    />
  );
}

export const cadTabProvider: TabProvider<'cad', CadState, CadTabResource, CadOpenArgs> =
  createTabProvider({
    kind: 'cad',
    mount: 'single',
    resourceKey: (state: CadState) => state.path,

    onBeforeOpen(args: CadOpenArgs, ctx: TabViewContext): CadState | null {
      const taskCtx = ctx as TaskTabContext;
      if (!taskCtx.workspacePath || taskCtx.getRemoteConnectionId?.()) return null;
      const path = resolveWorkspacePath(taskCtx.workspacePath, args.path);
      const browserSettings = getAppSettingValueSnapshot('browser');
      const profileId = normalizeBrowserProfileSelection(
        browserSettings?.defaultProfileId,
        browserSettings?.profiles
      );
      const session = browserSessionStore.createSession({
        projectId: taskCtx.projectId,
        workspaceId: taskCtx.workspaceId,
        taskId: taskCtx.taskId,
        profileId,
      });
      return {
        path,
        workspacePath: taskCtx.workspacePath,
        chatOpen: true,
        workspaceMode: '3d',
        browserId: session.browserId,
        session,
      };
    },

    initialize(entry: TabEntry<CadState>, handle: TabHandle): CadTabResource {
      return new CadTabResource(entry, handle);
    },

    dispose(_entry: TabEntry<CadState>, resource: CadTabResource): void {
      resource.dispose();
    },

    TabBarItem: CadTabBarItem,
    TabBarItemDragPreview: CadTabBarItemDragPreview,
    TabContent: CadTabContent,
  });

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

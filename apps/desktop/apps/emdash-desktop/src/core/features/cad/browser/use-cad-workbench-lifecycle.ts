import { useEffect, useMemo } from 'react';
import { cadModelContextKey } from '@core/features/cad/api/browser/cad-agent';
import type { CadModelIdentity } from '@core/features/cad/api/cad-model-state';
import { cadModelCatalogMemento } from '@core/features/cad/contributions/mementos';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import { relativeToWorkspace } from '@core/features/workspaces/api/browser/workspace-path';
import { useMemento } from '@core/primitives/mementos/react/use-memento';
import type { CadTabResource } from '../api/browser/cad-tab-resource';
import { cadOutputPath } from './cad-design-history-model';
import { recordFocusedCadArtifact, registerCadTaskRunRefreshHandler } from './cad-task-run-runtime';
import { ensureCadWorkbenchModel } from './cad-workbench-lifecycle';

export function useCadWorkbenchLifecycle(input: {
  resource: CadTabResource;
  task: TaskTabContext;
  sourcePath: string | null;
  focused: boolean;
}): void {
  const [, setCatalog] = useMemento(cadModelCatalogMemento);

  const relativePath = relativeToWorkspace(input.resource.workspacePath, input.resource.path);
  const contextKey = cadModelContextKey(relativePath);
  const discoveredSourcePath = input.sourcePath
    ? relativeToWorkspace(input.resource.workspacePath, input.sourcePath)
    : undefined;
  const fallbackIdentity = useMemo<CadModelIdentity>(
    () => ({
      contextKey,
      modelPath: cadOutputPath(relativePath),
      ...(discoveredSourcePath ? { sourcePath: discoveredSourcePath } : {}),
    }),
    [contextKey, discoveredSourcePath, relativePath]
  );
  const ownershipTarget = useMemo(
    () => ({
      projectId: input.task.projectId,
      taskId: input.task.taskId,
      contextKey,
    }),
    [contextKey, input.task.projectId, input.task.taskId]
  );

  useEffect(() => {
    setCatalog((current) =>
      ensureCadWorkbenchModel(current, fallbackIdentity, input.focused, new Date().toISOString())
    );
  }, [fallbackIdentity, input.focused, setCatalog]);

  useEffect(() => {
    if (!input.focused) return;
    recordFocusedCadArtifact(ownershipTarget);
  }, [input.focused, ownershipTarget]);

  useEffect(
    () => registerCadTaskRunRefreshHandler(ownershipTarget, input.resource.refreshViewer),
    [input.resource.refreshViewer, ownershipTarget]
  );
}

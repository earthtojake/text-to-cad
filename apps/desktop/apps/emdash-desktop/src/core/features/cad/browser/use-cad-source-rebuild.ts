import { useCallback, useEffect, useMemo, useState } from 'react';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import {
  preserveLastGoodModel,
  restoreLastGoodModel,
} from '@core/features/cad/api/browser/cad-last-good';
import {
  beginCadValidation,
  ensureCadModel,
  finishCadRun,
  finishCadValidation,
  type CadLastGoodSnapshot,
  type CadModelIdentity,
} from '@core/features/cad/api/cad-model-state';
import { CAD_VALIDATION_WIRE_TIMEOUT_MS } from '@core/features/cad/api/cad-validation';
import { cadModelCatalogMemento } from '@core/features/cad/contributions/mementos';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import { relativeToWorkspace } from '@core/features/workspaces/api/browser/workspace-path';
import { useMemento } from '@core/primitives/mementos/react/use-memento';
import type { CadTabResource } from '../api/browser/cad-tab-resource';
import {
  cadSourceRunHasRestorableFiles,
  resolveCadSourceRebuildModel,
} from './cad-source-rebuild-model';
import { acquireCadSourceRunLease } from './cad-source-run-lease';
import { acquireCadSourceRunOwnership, clearCadSourceRunOwnership } from './cad-task-run-runtime';

interface RebuildPreparationResult {
  success: boolean;
  error?: string;
}

export type CadSourceRebuildResult = { success: true } | { success: false; error: string };

export function useCadSourceRebuild(input: {
  resource: CadTabResource;
  task: TaskTabContext;
  sourcePath: string;
}) {
  const connectionId = input.task.getRemoteConnectionId?.();
  const sourceRelativePath = relativeToWorkspace(input.resource.workspacePath, input.sourcePath);
  const openedRelativePath = relativeToWorkspace(input.resource.workspacePath, input.resource.path);
  const [catalog, setCatalog] = useMemento(cadModelCatalogMemento);
  const rebuildModel = useMemo(
    () =>
      resolveCadSourceRebuildModel({
        catalog,
        openedPath: openedRelativePath,
        sourcePath: sourceRelativePath,
      }),
    [catalog, openedRelativePath, sourceRelativePath]
  );
  const identity: CadModelIdentity = rebuildModel.identity;
  const modelRecord = rebuildModel.model;
  const ownershipTarget = useMemo(
    () => ({
      projectId: input.task.projectId,
      taskId: input.task.taskId,
      contextKey: identity.contextKey,
    }),
    [identity.contextKey, input.task.projectId, input.task.taskId]
  );
  const runInProgress =
    modelRecord?.run.status === 'generating' || modelRecord?.run.status === 'validating';
  const [rebuilding, setRebuilding] = useState(false);

  useEffect(() => {
    setCatalog((current) => ensureCadModel(current, identity, new Date().toISOString()));
  }, [identity, setCatalog]);

  const rebuildSource = useCallback(
    async (options: {
      prepare?: () => Promise<RebuildPreparationResult>;
      restoreSourceOnFailure: boolean;
    }): Promise<CadSourceRebuildResult> => {
      if (rebuilding || runInProgress) {
        return { success: false, error: 'Another model edit is already running.' };
      }
      setRebuilding(true);
      const runId = crypto.randomUUID();
      const startedAt = new Date().toISOString();
      let lastGood: CadLastGoodSnapshot | undefined;
      let validationStarted = false;
      let ownsSourceRun = false;
      try {
        lastGood = await preserveLastGoodModel({
          workspacePath: input.resource.workspacePath,
          modelPath: identity.modelPath,
          sourcePath: identity.sourcePath,
          contextKey: identity.contextKey,
          runId,
          recordedAt: startedAt,
        });
        if (!acquireCadSourceRunOwnership(ownershipTarget, runId)) {
          return {
            success: false,
            error: 'Another model edit started while files were backed up.',
          };
        }
        ownsSourceRun = true;
        const started = acquireCadSourceRunLease(setCatalog, identity, {
          id: runId,
          startedAt,
          ...(lastGood ? { lastGood } : {}),
        });
        if (!started) {
          return {
            success: false,
            error: 'Another model edit started while files were backed up.',
          };
        }

        const preparation = options.prepare ? await options.prepare() : { success: true };
        if (!preparation.success) {
          setCatalog((current) =>
            finishCadRun(current, identity.contextKey, 'failed', new Date().toISOString())
          );
          return {
            success: false,
            error: preparation.error ?? 'Could not prepare the model edit.',
          };
        }

        setCatalog((current) => beginCadValidation(current, identity.contextKey));
        validationStarted = true;
        const result = await (
          await getBrowserClient()
        ).rebuildCadModel(
          {
            workspacePath: input.resource.workspacePath,
            filePath: input.sourcePath,
          },
          { timeoutMs: CAD_VALIDATION_WIRE_TIMEOUT_MS }
        );
        setCatalog((current) =>
          finishCadValidation(current, identity.contextKey, result, new Date().toISOString())
        );
        let restoreError = '';
        if (
          !result.success &&
          cadSourceRunHasRestorableFiles(lastGood, options.restoreSourceOnFailure)
        ) {
          try {
            await restoreLastGoodModel({
              workspacePath: input.resource.workspacePath,
              snapshot: lastGood,
              sshConnectionId: connectionId,
              restoreSource: options.restoreSourceOnFailure,
            });
          } catch (error) {
            restoreError = error instanceof Error ? error.message : 'Could not restore the model.';
          }
        }
        input.resource.refreshViewer();
        if (!result.success) {
          return {
            success: false,
            error: restoreError
              ? `${result.error} ${restoreError}`
              : options.restoreSourceOnFailure
                ? `${result.error} The last valid source and 3D model were restored when available.`
                : `${result.error} The source remains open; the last valid 3D model was kept when available.`,
          };
        }
        return { success: true };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Could not rebuild the model.';
        setCatalog((current) =>
          validationStarted
            ? finishCadValidation(
                current,
                identity.contextKey,
                { success: false, error: message },
                new Date().toISOString()
              )
            : finishCadRun(current, identity.contextKey, 'failed', new Date().toISOString())
        );
        let restoreError = '';
        if (cadSourceRunHasRestorableFiles(lastGood, options.restoreSourceOnFailure)) {
          try {
            await restoreLastGoodModel({
              workspacePath: input.resource.workspacePath,
              snapshot: lastGood,
              sshConnectionId: connectionId,
              restoreSource: options.restoreSourceOnFailure,
            });
          } catch (restoreFailure) {
            restoreError =
              restoreFailure instanceof Error
                ? restoreFailure.message
                : 'Could not restore the model.';
          }
        }
        input.resource.refreshViewer();
        return {
          success: false,
          error: restoreError ? `${message} ${restoreError}` : message,
        };
      } finally {
        if (ownsSourceRun) clearCadSourceRunOwnership(ownershipTarget, runId);
        setRebuilding(false);
      }
    },
    [
      connectionId,
      identity,
      input.resource,
      input.sourcePath,
      ownershipTarget,
      rebuilding,
      runInProgress,
      setCatalog,
    ]
  );

  return { rebuildSource, rebuilding, runInProgress };
}

import { toast } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import {
  buildCadFirstRoutingContext,
  buildHardcoreViewerContext,
} from '@core/features/cad/api/browser/cad-agent';
import {
  preserveLastGoodModel,
  restoreLastGoodModel,
} from '@core/features/cad/api/browser/cad-last-good';
import {
  beginCadValidation,
  finishCadRun,
  finishCadValidation,
  interruptRecoveredCadRun,
} from '@core/features/cad/api/cad-model-state';
import { CAD_VALIDATION_WIRE_TIMEOUT_MS } from '@core/features/cad/api/cad-validation';
import {
  cadModelCatalogMemento,
  type CadModelCatalog,
  type CadModelRecord,
} from '@core/features/cad/contributions/mementos';
import {
  combineWorkbenchHiddenContext,
  registerWorkbenchChatSubmissionHandler,
} from '@core/features/conversations/api/browser/chat/workbench-chat-submit-bridge';
import {
  acquireIntegratedAgentSession,
  type IntegratedAgentSession,
} from '@core/features/conversations/api/browser/integrated-agent-session';
import {
  useConversations,
  useTaskComposition,
} from '@core/features/workbench/api/browser/task-composition-context';
import { useMemento } from '@core/primitives/mementos/react/use-memento';
import { useCadArtifactReveal } from './cad-artifact-reveal';
import {
  clearCadTaskRunOwnership,
  getFocusedCadArtifact,
  getCadTaskRunOwnership,
  isCadSourceRunLocallyOwned,
  recordCadTaskRunOwnership,
  refreshCadTaskRunArtifact,
} from './cad-task-run-runtime';
import {
  activeCadWorkbenchTarget,
  abortPreparedCadWorkbenchRun,
  cadRecoveredRunIsAbandoned,
  cadWorkbenchTurnIsComplete,
  prepareCadWorkbenchRun,
  validateCadWorkbenchArtifact,
} from './cad-workbench-lifecycle';

/**
 * Task-owned CAD run supervision. It intentionally lives above panes/tabs so
 * changing the focused artifact or chat cannot abandon validation or recovery.
 */
export const CadTaskRunLifecycle = observer(function CadTaskRunLifecycle() {
  const task = useTaskComposition();
  const conversations = useConversations();
  const [catalog, setCatalog] = useMemento(cadModelCatalogMemento);
  const catalogRef = useRef(catalog);
  catalogRef.current = catalog;
  const preparingRef = useRef(false);
  const workspacePath = task.workspace?.path;
  const connectionId = task.workspace?.sshConnectionId;
  const isTrackedArtifact = useCallback(
    (relativePath: string) =>
      Object.values(catalogRef.current.models).some(
        (model) =>
          model.modelPath === relativePath ||
          model.artifacts.some((artifact) => artifact.path === relativePath)
      ),
    []
  );
  useCadArtifactReveal(task, conversations, isTrackedArtifact);

  useEffect(() => {
    const target = { projectId: task.projectId, taskId: task.taskId };
    return registerWorkbenchChatSubmissionHandler(target, async (submission) => {
      if (!workspacePath) {
        return { success: false, error: 'The project workspace is not available.' };
      }
      if (submission.agentIsWorking) {
        // Prompts sent mid-turn are queued by the runtime and start when the
        // current turn ends, the same way Codex and Claude Code queue them. The
        // per-run backup/validation preparation is skipped for a queued prompt:
        // it needs the model files at rest, which they are not while an agent is
        // editing them. The reveal ledger still tracks whatever that turn writes.
        return { success: true, hiddenContext: buildCadFirstRoutingContext() };
      }
      if (preparingRef.current) {
        return { success: false, error: 'The current CAD change is still being prepared.' };
      }

      const current = catalogRef.current;
      const activeTarget = activeCadWorkbenchTarget(
        current,
        getFocusedCadArtifact({ projectId: task.projectId, taskId: task.taskId })
      );
      // A new task without a focused engineering artifact stays flexible but
      // defaults ambiguous physical-object requests to CAD. Once a model is
      // focused, every turn is routed through its backup/validation lifecycle
      // even if its viewer tab closes.
      if (activeTarget.status === 'none') {
        return { success: true, hiddenContext: buildCadFirstRoutingContext() };
      }
      if (activeTarget.status === 'missing') {
        return { success: false, error: 'The focused CAD artifact is no longer available.' };
      }

      preparingRef.current = true;
      try {
        const { identity, modelFiles } = activeTarget;
        const runId = crypto.randomUUID();
        const prepared = await prepareCadWorkbenchRun({
          catalog: current,
          identity,
          workspacePath,
          conversationId: submission.conversationId,
          prompt: submission.text,
          modelFiles,
          runId,
          startedAt: new Date().toISOString(),
          ...(connectionId ? { sshConnectionId: connectionId } : {}),
          getLatestCatalog: () => catalogRef.current,
          preserve: preserveLastGoodModel,
        });
        if (!prepared.success) return prepared;

        recordCadTaskRunOwnership({
          projectId: task.projectId,
          taskId: task.taskId,
          contextKey: identity.contextKey,
          runId: prepared.runId,
          conversationId: submission.conversationId,
          messageCountBeforeSubmit: submission.messageCountBeforeSubmit,
        });
        catalogRef.current = prepared.catalog;
        setCatalog(prepared.catalog);
        return {
          success: true,
          hiddenContext: combineWorkbenchHiddenContext(
            prepared.hiddenContext,
            buildHardcoreViewerContext()
          ),
          onDispatchFailure: async () => {
            const updateCatalog = (update: (current: CadModelCatalog) => CadModelCatalog) => {
              setCatalog((current) => {
                const next = update(current);
                catalogRef.current = next;
                return next;
              });
            };
            try {
              const aborted = await abortPreparedCadWorkbenchRun({
                contextKey: identity.contextKey,
                runId: prepared.runId,
                workspacePath,
                ...(connectionId ? { sshConnectionId: connectionId } : {}),
                getCatalog: () => catalogRef.current,
                updateCatalog,
                restore: restoreLastGoodModel,
              });
              return aborted.restoreError
                ? {
                    success: false as const,
                    error: `The saved CAD files could not be restored: ${aborted.restoreError}`,
                  }
                : { success: true as const };
            } catch (error) {
              updateCatalog((current) =>
                interruptRecoveredCadRun(
                  current,
                  identity.contextKey,
                  prepared.runId,
                  new Date().toISOString()
                )
              );
              return {
                success: false as const,
                error:
                  error instanceof Error
                    ? `The CAD edit lock was released, but rollback failed: ${error.message}`
                    : 'The CAD edit lock was released, but rollback failed.',
              };
            } finally {
              clearCadTaskRunOwnership(
                {
                  projectId: task.projectId,
                  taskId: task.taskId,
                  contextKey: identity.contextKey,
                },
                prepared.runId
              );
              refreshCadTaskRunArtifact({
                projectId: task.projectId,
                taskId: task.taskId,
                contextKey: identity.contextKey,
              });
            }
          },
        };
      } finally {
        preparingRef.current = false;
      }
    });
  }, [connectionId, setCatalog, task.projectId, task.taskId, workspacePath]);

  if (!workspacePath) return null;

  const runningModels = Object.values(catalog.models).filter(
    (model) =>
      model.run.id && (model.run.status === 'generating' || model.run.status === 'validating')
  );
  return (
    <>
      {runningModels.map((model) =>
        model.run.origin === 'source' ? (
          <RecoveredCadSourceRunWatcher
            key={`${model.contextKey}:${model.run.id}`}
            projectId={task.projectId}
            taskId={task.taskId}
            model={model}
            setCatalog={setCatalog}
          />
        ) : (
          <CadTaskRunWatcher
            key={`${model.contextKey}:${model.run.id}`}
            projectId={task.projectId}
            taskId={task.taskId}
            workspacePath={workspacePath}
            connectionId={task.workspace?.sshConnectionId}
            model={model}
            setCatalog={setCatalog}
          />
        )
      )}
    </>
  );
});

function RecoveredCadSourceRunWatcher({
  projectId,
  taskId,
  model,
  setCatalog,
}: {
  projectId: string;
  taskId: string;
  model: CadModelRecord;
  setCatalog: (next: CadModelCatalog | ((current: CadModelCatalog) => CadModelCatalog)) => void;
}) {
  const runId = model.run.id!;
  const ownershipTarget = useMemo(
    () => ({ projectId, taskId, contextKey: model.contextKey }),
    [model.contextKey, projectId, taskId]
  );
  const locallyOwned = isCadSourceRunLocallyOwned(ownershipTarget, runId);

  useEffect(() => {
    if (locallyOwned) return;
    // Direct source rebuild promises cannot survive a renderer restart. Clear
    // only their stale catalog lease; canonical reconciliation will inspect the
    // STEP currently on disk and must never restore an old session backup.
    setCatalog((current) =>
      interruptRecoveredCadRun(current, model.contextKey, runId, new Date().toISOString())
    );
  }, [locallyOwned, model.contextKey, runId, setCatalog]);

  return null;
}

const CadTaskRunWatcher = observer(function CadTaskRunWatcher({
  projectId,
  taskId,
  workspacePath,
  connectionId,
  model,
  setCatalog,
}: {
  projectId: string;
  taskId: string;
  workspacePath: string;
  connectionId?: string;
  model: CadModelRecord;
  setCatalog: (next: CadModelCatalog | ((current: CadModelCatalog) => CadModelCatalog)) => void;
}) {
  const conversations = useConversations();
  const runId = model.run.id!;
  const conversationId = model.run.conversationId;
  const conversation = conversationId
    ? conversations.conversations.get(conversationId)?.data
    : null;
  const agentStatus = conversation?.agentStatus ?? null;
  const ownershipTarget = useMemo(
    () => ({ projectId, taskId, contextKey: model.contextKey }),
    [model.contextKey, projectId, taskId]
  );
  const ownership = getCadTaskRunOwnership(ownershipTarget);
  const locallyOwned = ownership?.runId === runId;
  const observedWorking = useRef(false);
  const settling = useRef(false);
  const [session, setSession] = useState<IntegratedAgentSession | null>(null);

  const updateCatalog = useCallback(
    (update: (current: CadModelCatalog) => CadModelCatalog) => setCatalog(update),
    [setCatalog]
  );

  useEffect(() => {
    setSession(null);
    if (!conversationId) return;
    const acquired = acquireIntegratedAgentSession({ conversationId, projectId, taskId });
    setSession(acquired);
    return () => acquired.dispose();
  }, [conversationId, projectId, taskId]);

  const isWorking = session?.isWorking ?? false;
  useEffect(() => {
    if (isWorking) observedWorking.current = true;
  }, [isWorking]);

  useEffect(() => {
    if (settling.current || session?.isLoading) return;
    const lifecycleStatus = session?.status ?? agentStatus;

    const finishFailedRun = async (status: 'failed' | 'interrupted') => {
      if (settling.current) return;
      settling.current = true;
      let restoreError = '';
      if (
        locallyOwned &&
        model.lastGood &&
        (model.lastGood.backupPath || model.lastGood.sourceBackupPath)
      ) {
        try {
          await restoreLastGoodModel({
            workspacePath,
            snapshot: model.lastGood,
            ...(connectionId ? { sshConnectionId: connectionId } : {}),
          });
        } catch (error) {
          restoreError =
            error instanceof Error ? error.message : 'Could not restore the CAD files.';
        }
      }
      updateCatalog((current) =>
        finishCadRun(current, model.contextKey, status, new Date().toISOString())
      );
      clearCadTaskRunOwnership(ownershipTarget, runId);
      refreshCadTaskRunArtifact(ownershipTarget);
      if (restoreError) {
        toast.error('Could not restore the previous CAD revision', {
          description: restoreError,
        });
      }
    };

    if (
      model.run.status === 'generating' &&
      (lifecycleStatus === 'error' || agentStatus === 'error')
    ) {
      void finishFailedRun('failed');
      return;
    }
    if (
      model.run.status === 'generating' &&
      observedWorking.current &&
      !isWorking &&
      lifecycleStatus === 'idle' &&
      agentStatus === 'idle'
    ) {
      void finishFailedRun('interrupted');
      return;
    }
    if (
      cadRecoveredRunIsAbandoned({
        runStatus: model.run.status,
        restoredRun: !locallyOwned,
        sessionReady: session !== null && !session.isLoading,
        sessionWorking: isWorking,
        sessionStatus: session?.status,
        agentStatus,
      })
    ) {
      // A renderer restart loses local run ownership, but the open/restart
      // bridge separately reconciles the canonical artifact on disk. Retire
      // the stale run without overwriting that artifact from an old backup.
      settling.current = true;
      updateCatalog((current) =>
        finishCadRun(current, model.contextKey, 'interrupted', new Date().toISOString())
      );
      return;
    }

    const shouldValidate =
      model.run.status === 'validating' ||
      cadWorkbenchTurnIsComplete({
        status: lifecycleStatus,
        agentStatus,
        observedWorking: observedWorking.current,
        restoredRun: !locallyOwned,
        messageCountBeforeSubmit: ownership?.messageCountBeforeSubmit,
        currentMessageCount: session?.messageCount,
      });
    if (!shouldValidate) return;
    settling.current = true;
    if (model.run.status === 'generating') {
      updateCatalog((current) => beginCadValidation(current, model.contextKey));
    }
    void validateCadWorkbenchArtifact({
      workspacePath,
      modelPath: model.modelPath,
      ...(model.sourcePath ? { sourcePath: model.sourcePath } : {}),
      snapshot: model.lastGood,
      restoreOnFailure: locallyOwned,
      ...(connectionId ? { sshConnectionId: connectionId } : {}),
      validate: async (validationInput) =>
        (await getBrowserClient()).validateCadModel(validationInput, {
          timeoutMs: CAD_VALIDATION_WIRE_TIMEOUT_MS,
        }),
      rebuild: async (rebuildInput) =>
        (await getBrowserClient()).rebuildCadModel(rebuildInput, {
          timeoutMs: CAD_VALIDATION_WIRE_TIMEOUT_MS,
        }),
      restore: restoreLastGoodModel,
    })
      .then(({ result, restored, restoreError }) => {
        updateCatalog((current) =>
          finishCadValidation(current, model.contextKey, result, new Date().toISOString())
        );
        clearCadTaskRunOwnership(ownershipTarget, runId);
        refreshCadTaskRunArtifact(ownershipTarget);
        if (!result.success) {
          toast.error('The CAD change did not validate', {
            description: restoreError
              ? `${result.error} ${restoreError}`
              : restored
                ? `${result.error} The previous CAD files were restored.`
                : result.error,
          });
        }
      })
      .catch((error) => {
        // The lifecycle helper converts validation/rebuild/restore failures
        // into result objects. This is a final guard against a stuck run if an
        // unexpected renderer error escapes those transaction boundaries.
        updateCatalog((current) =>
          finishCadRun(current, model.contextKey, 'failed', new Date().toISOString())
        );
        clearCadTaskRunOwnership(ownershipTarget, runId);
        refreshCadTaskRunArtifact(ownershipTarget);
        toast.error('The CAD change could not be finalized', {
          description: error instanceof Error ? error.message : String(error),
        });
      });
  }, [
    agentStatus,
    connectionId,
    isWorking,
    locallyOwned,
    model,
    ownership?.messageCountBeforeSubmit,
    ownershipTarget,
    runId,
    session,
    updateCatalog,
    workspacePath,
  ]);

  return null;
});

import type { CadValidationResult } from '@core/features/browser/api';
import { buildCadAgentContext } from '@core/features/cad/api/browser/cad-agent';
import type { CadLastGoodSnapshot } from '@core/features/cad/api/cad-model-state';
import {
  cadEditAvailability,
  ensureCadModel,
  interruptRecoveredCadRun,
  registerCadModelConversation,
  startCadRun,
  type CadModelIdentity,
} from '@core/features/cad/api/cad-model-state';
import type { CadModelCatalog } from '@core/features/cad/contributions/mementos';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';

export type CadWorkbenchRunPreparation =
  | {
      success: true;
      catalog: CadModelCatalog;
      runId: string;
      hiddenContext: string;
    }
  | { success: false; error: string };

export type ActiveCadWorkbenchTarget =
  | { status: 'none' }
  | { status: 'missing'; contextKey: string }
  | {
      status: 'ready';
      identity: CadModelIdentity;
      modelFiles: string[];
    };

/**
 * Resolve one explicit task-level target instead of relying on whichever CAD
 * pane happened to register its effect last. The active key is retained when
 * focus returns to chat, so multiple visible artifact panes remain unambiguous.
 */
export function activeCadWorkbenchTarget(
  catalog: CadModelCatalog,
  preferredContextKey?: string
): ActiveCadWorkbenchTarget {
  // An explicit pane focus is authoritative. If that artifact disappeared,
  // fail closed instead of silently redirecting the turn to another model.
  if (preferredContextKey && !catalog.models[preferredContextKey]) {
    return { status: 'missing', contextKey: preferredContextKey };
  }
  const contextKey = preferredContextKey ?? catalog.activeModelKey;
  if (!contextKey) return { status: 'none' };
  const model = catalog.models[contextKey];
  if (!model) return { status: 'missing', contextKey };
  return {
    status: 'ready',
    identity: {
      contextKey,
      modelPath: model.modelPath,
      ...(model.sourcePath ? { sourcePath: model.sourcePath } : {}),
    },
    modelFiles: model.artifacts.map(({ path }) => path),
  };
}

export function ensureCadWorkbenchModel(
  catalog: CadModelCatalog,
  identity: CadModelIdentity,
  focused: boolean,
  now: string
): CadModelCatalog {
  const previousActiveKey = catalog.activeModelKey;
  const ensured = ensureCadModel(catalog, identity, now);
  if (focused || !previousActiveKey || previousActiveKey === identity.contextKey) return ensured;
  return { ...ensured, activeModelKey: previousActiveKey };
}

export function cadWorkbenchTurnIsComplete(input: {
  status: string | null | undefined;
  agentStatus: string | null | undefined;
  observedWorking: boolean;
  restoredRun: boolean;
  messageCountBeforeSubmit?: number;
  currentMessageCount?: number;
}): boolean {
  const terminal = input.status === 'completed' || input.agentStatus === 'completed';
  if (!terminal) return false;
  // submitPrompt immediately adds one optimistic user item. Requiring another
  // item prevents the previous turn's `completed` status from validating before
  // the new provider turn has even started.
  const completedNewTurn =
    input.messageCountBeforeSubmit !== undefined &&
    input.currentMessageCount !== undefined &&
    input.currentMessageCount > input.messageCountBeforeSubmit + 1;
  return input.observedWorking || completedNewTurn || input.restoredRun;
}

export function cadRecoveredRunIsAbandoned(input: {
  runStatus: string;
  restoredRun: boolean;
  sessionReady: boolean;
  sessionWorking: boolean;
  sessionStatus: string | null | undefined;
  agentStatus: string | null | undefined;
}): boolean {
  return (
    input.runStatus === 'generating' &&
    input.restoredRun &&
    input.sessionReady &&
    !input.sessionWorking &&
    input.sessionStatus === 'idle' &&
    (input.agentStatus === null || input.agentStatus === undefined || input.agentStatus === 'idle')
  );
}

export async function prepareCadWorkbenchRun(input: {
  catalog: CadModelCatalog;
  identity: CadModelIdentity;
  workspacePath: string;
  conversationId: string;
  prompt: string;
  modelFiles: readonly string[];
  runId: string;
  startedAt: string;
  sshConnectionId?: string;
  getLatestCatalog?: () => CadModelCatalog;
  preserve: (options: {
    workspacePath: string;
    modelPath: string;
    sourcePath?: string;
    contextKey: string;
    runId: string;
    sshConnectionId?: string;
    recordedAt: string;
  }) => Promise<CadLastGoodSnapshot | undefined>;
}): Promise<CadWorkbenchRunPreparation> {
  let catalog = ensureCadModel(input.catalog, input.identity, input.startedAt);
  let model = catalog.models[input.identity.contextKey]!;
  if (!model.conversations[input.conversationId]) {
    catalog = registerCadModelConversation(catalog, input.identity.contextKey, {
      id: input.conversationId,
      type: Object.keys(model.conversations).length === 0 ? 'design' : 'custom',
      createdAt: input.startedAt,
    });
    model = catalog.models[input.identity.contextKey]!;
  }

  const availability = cadEditAvailability(
    catalog,
    input.identity.contextKey,
    input.conversationId
  );
  if (!availability.allowed) {
    return {
      success: false,
      error:
        availability.reason === 'run-in-progress'
          ? 'Another CAD change is already generating or validating.'
          : 'The focused CAD artifact is no longer available.',
    };
  }

  let lastGood: CadLastGoodSnapshot | undefined;
  try {
    lastGood = await input.preserve({
      workspacePath: input.workspacePath,
      modelPath: model.modelPath,
      ...(model.sourcePath ? { sourcePath: model.sourcePath } : {}),
      contextKey: input.identity.contextKey,
      runId: input.runId,
      ...(input.sshConnectionId ? { sshConnectionId: input.sshConnectionId } : {}),
      recordedAt: input.startedAt,
    });
  } catch (error) {
    return {
      success: false,
      error:
        error instanceof Error
          ? `Could not preserve the current CAD files: ${error.message}`
          : 'Could not preserve the current CAD files.',
    };
  }

  // Backing up can overlap a viewer/open reconciliation. Rebase the run on
  // the newest catalog so a prompt never writes stale revision metadata back.
  if (input.getLatestCatalog) {
    catalog = ensureCadModel(input.getLatestCatalog(), input.identity, input.startedAt);
    model = catalog.models[input.identity.contextKey]!;
    if (!model.conversations[input.conversationId]) {
      catalog = registerCadModelConversation(catalog, input.identity.contextKey, {
        id: input.conversationId,
        type: Object.keys(model.conversations).length === 0 ? 'design' : 'custom',
        createdAt: input.startedAt,
      });
      model = catalog.models[input.identity.contextKey]!;
    }
    const latestAvailability = cadEditAvailability(
      catalog,
      input.identity.contextKey,
      input.conversationId
    );
    if (!latestAvailability.allowed) {
      return {
        success: false,
        error:
          latestAvailability.reason === 'run-in-progress'
            ? 'Another CAD change is already generating or validating.'
            : 'The focused CAD artifact is no longer available.',
      };
    }
  }

  const runningCatalog = startCadRun(catalog, input.identity, {
    id: input.runId,
    conversationId: input.conversationId,
    prompt: input.prompt || 'Review the attached CAD context.',
    startedAt: input.startedAt,
    ...(lastGood ? { lastGood } : {}),
  });
  if (runningCatalog === catalog) {
    return { success: false, error: 'Another CAD change started before this request.' };
  }

  const conversationType =
    runningCatalog.models[input.identity.contextKey]?.conversations[input.conversationId]?.type ??
    'custom';
  return {
    success: true,
    catalog: runningCatalog,
    runId: input.runId,
    hiddenContext: buildCadAgentContext({
      relativePath: model.modelPath,
      modelFiles:
        input.modelFiles.length > 0 ? input.modelFiles : model.artifacts.map(({ path }) => path),
      revisionId: model.revisionId,
      modelHash: model.modelHash,
      sourceHash: model.sourceHash,
      conversationType,
      canEditGeometry: true,
    }),
  };
}

export async function validateCadWorkbenchArtifact(input: {
  workspacePath: string;
  modelPath: string;
  sourcePath?: string;
  snapshot?: CadLastGoodSnapshot;
  restoreOnFailure: boolean;
  sshConnectionId?: string;
  validate: (input: {
    workspacePath: string;
    filePath: string;
    sourcePath?: string;
  }) => Promise<CadValidationResult>;
  rebuild?: (input: { workspacePath: string; filePath: string }) => Promise<CadValidationResult>;
  restore: (input: {
    workspacePath: string;
    snapshot: CadLastGoodSnapshot;
    sshConnectionId?: string;
  }) => Promise<void>;
}): Promise<{ result: CadValidationResult; restored: boolean; restoreError?: string }> {
  let result: CadValidationResult;
  try {
    result = await input.validate({
      workspacePath: input.workspacePath,
      // The accepted on-disk artifact is canonical. Completing an agent turn
      // must inspect it, never execute its linked generator as a side effect.
      filePath: resolveWorkspacePath(input.workspacePath, input.modelPath),
      ...(input.sourcePath
        ? { sourcePath: resolveWorkspacePath(input.workspacePath, input.sourcePath) }
        : {}),
    });
  } catch (error) {
    result = {
      success: false,
      error: error instanceof Error ? error.message : 'CAD validation failed.',
    };
  }

  const sourcePath = input.sourcePath;
  if (
    result.success &&
    sourcePath !== undefined &&
    input.snapshot?.sourceHash !== undefined &&
    result.artifact.sourceHash !== undefined &&
    result.artifact.sourceHash !== input.snapshot.sourceHash &&
    input.snapshot.modelHash !== undefined &&
    result.artifact.modelHash === input.snapshot.modelHash
  ) {
    const sourceHashBeforeRebuild = result.artifact.sourceHash;
    const modelHashBeforeRun = input.snapshot.modelHash;
    if (!input.rebuild) {
      result = {
        success: false,
        error: 'The model source changed, but its canonical STEP was not rebuilt.',
      };
    } else {
      try {
        const rebuilt = await input.rebuild({
          workspacePath: input.workspacePath,
          filePath: resolveWorkspacePath(input.workspacePath, sourcePath),
        });
        if (rebuilt.success && rebuilt.artifact.sourceHash !== sourceHashBeforeRebuild) {
          result = {
            success: false,
            error: 'The model source changed again while its canonical STEP was rebuilding.',
          };
        } else if (rebuilt.success && rebuilt.artifact.modelHash === modelHashBeforeRun) {
          result = {
            success: false,
            error: 'The model source changed, but rebuilding did not update the canonical STEP.',
          };
        } else {
          result = rebuilt;
        }
      } catch (error) {
        result = {
          success: false,
          error: error instanceof Error ? error.message : 'CAD rebuild failed.',
        };
      }
    }
  }

  if (
    result.success ||
    !input.restoreOnFailure ||
    !input.snapshot ||
    (!input.snapshot.backupPath && !input.snapshot.sourceBackupPath)
  ) {
    return { result, restored: false };
  }

  try {
    await input.restore({
      workspacePath: input.workspacePath,
      snapshot: input.snapshot,
      ...(input.sshConnectionId ? { sshConnectionId: input.sshConnectionId } : {}),
    });
    return { result, restored: true };
  } catch (error) {
    return {
      result,
      restored: false,
      restoreError: error instanceof Error ? error.message : 'Could not restore the CAD files.',
    };
  }
}

export async function abortPreparedCadWorkbenchRun(input: {
  contextKey: string;
  runId: string;
  workspacePath: string;
  sshConnectionId?: string;
  getCatalog: () => CadModelCatalog;
  updateCatalog: (update: (current: CadModelCatalog) => CadModelCatalog) => void;
  restore: (input: {
    workspacePath: string;
    snapshot: CadLastGoodSnapshot;
    sshConnectionId?: string;
  }) => Promise<void>;
}): Promise<{
  aborted: boolean;
  restored: boolean;
  restoreError?: string;
}> {
  const model = input.getCatalog().models[input.contextKey];
  if (
    !model ||
    model.run.id !== input.runId ||
    (model.run.status !== 'generating' && model.run.status !== 'validating')
  ) {
    return { aborted: false, restored: false };
  }

  let restored = false;
  let restoreError: string | undefined;
  if (model.lastGood && (model.lastGood.backupPath || model.lastGood.sourceBackupPath)) {
    try {
      await input.restore({
        workspacePath: input.workspacePath,
        snapshot: model.lastGood,
        ...(input.sshConnectionId ? { sshConnectionId: input.sshConnectionId } : {}),
      });
      restored = true;
    } catch (error) {
      restoreError = error instanceof Error ? error.message : 'Could not restore the CAD files.';
    }
  }

  input.updateCatalog((current) =>
    interruptRecoveredCadRun(current, input.contextKey, input.runId, new Date().toISOString())
  );
  return {
    aborted: true,
    restored,
    ...(restoreError ? { restoreError } : {}),
  };
}

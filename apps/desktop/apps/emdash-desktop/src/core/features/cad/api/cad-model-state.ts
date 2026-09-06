import type {
  CadModelCatalog,
  CadModelConversationType,
  CadModelRecord,
  CadRunStatus,
} from '@core/features/cad/contributions/mementos';

export interface CadModelIdentity {
  contextKey: string;
  modelPath: string;
  sourcePath?: string;
}

export interface CadLastGoodSnapshot {
  modelPath: string;
  backupPath?: string;
  /** The `<model>.step.json` sidecar that belonged to the accepted STEP, if any. */
  sidecarPath?: string;
  sidecarBackupPath?: string;
  sourcePath?: string;
  sourceBackupPath?: string;
  recordedAt: string;
  validationStatus: 'passed' | 'unknown';
  revisionId?: string;
  modelHash?: string;
  sourceHash?: string;
}

export interface CadArtifactIdentity {
  revisionId: string;
  modelPath: string;
  modelHash: string;
  sourcePath?: string;
  sourceHash?: string;
}

export type CadEditAvailability =
  | { allowed: true }
  | { allowed: false; reason: 'missing-model' | 'run-in-progress' };

export type CadEditingConversationSwitch =
  | { status: 'updated' | 'unchanged'; catalog: CadModelCatalog; stale: boolean }
  | { status: 'missing' | 'run-in-progress'; catalog: CadModelCatalog; stale: false };

export type CadModelConversationRemoval =
  | { status: 'removed'; catalog: CadModelCatalog }
  | {
      status: 'missing' | 'last-conversation' | 'editing-conversation' | 'run-in-progress';
      catalog: CadModelCatalog;
    };

export type CadModelConversationArchive =
  | { status: 'archived' | 'restored' | 'unchanged'; catalog: CadModelCatalog }
  | {
      status: 'missing' | 'last-active-conversation' | 'run-in-progress';
      catalog: CadModelCatalog;
    };

export function ensureCadModel(
  catalog: CadModelCatalog,
  identity: CadModelIdentity,
  now: string
): CadModelCatalog {
  const existing = catalog.models[identity.contextKey];
  const model = modelRecord(existing, identity, now);
  if (catalog.activeModelKey === identity.contextKey && existing === model) return catalog;
  return {
    ...catalog,
    activeModelKey: identity.contextKey,
    models: { ...catalog.models, [identity.contextKey]: model },
  };
}

export function reconcileCadModelConversations(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationIds: readonly string[],
  now: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current || conversationIds.length === 0) return catalog;
  const conversations = { ...current.conversations };
  let changed = false;
  for (const conversationId of conversationIds) {
    if (conversations[conversationId]) continue;
    const hasDesign = Object.values(conversations).some(
      (conversation) => conversation.type === 'design'
    );
    conversations[conversationId] = {
      id: conversationId,
      type: hasDesign ? 'custom' : 'design',
      createdAt: now,
      updatedAt: now,
    };
    changed = true;
  }
  const available = new Set(conversationIds);
  const activeConversationIds = conversationIds.filter(
    (conversationId) => !conversations[conversationId]?.archivedAt
  );
  const activeConversationId =
    current.activeConversationId && activeConversationIds.includes(current.activeConversationId)
      ? current.activeConversationId
      : (activeConversationIds[0] ?? conversationIds[0]);
  const editingConversationId =
    current.editingConversationId && activeConversationIds.includes(current.editingConversationId)
      ? current.editingConversationId
      : (Object.values(conversations).find(
          (conversation) =>
            available.has(conversation.id) &&
            !conversation.archivedAt &&
            conversation.type === 'design'
        )?.id ?? activeConversationIds[0]);
  if (
    !changed &&
    current.activeConversationId === activeConversationId &&
    current.editingConversationId === editingConversationId
  ) {
    return catalog;
  }
  return replaceModel(catalog, contextKey, {
    ...current,
    conversations,
    ...(activeConversationId ? { activeConversationId } : {}),
    ...(editingConversationId ? { editingConversationId } : {}),
    updatedAt: now,
  });
}

export function registerCadModelConversation(
  catalog: CadModelCatalog,
  contextKey: string,
  input: { id: string; type: CadModelConversationType; createdAt: string }
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current) return catalog;
  const isFirst = Object.keys(current.conversations).length === 0;
  return replaceModel(catalog, contextKey, {
    ...current,
    conversations: {
      ...current.conversations,
      [input.id]: {
        id: input.id,
        type: input.type,
        createdAt: input.createdAt,
        updatedAt: input.createdAt,
      },
    },
    activeConversationId: input.id,
    ...(!current.editingConversationId || isFirst ? { editingConversationId: input.id } : {}),
    updatedAt: input.createdAt,
  });
}

export function selectCadModelConversation(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  selectedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current?.conversations[conversationId] || current.conversations[conversationId].archivedAt) {
    return catalog;
  }
  if (current.activeConversationId === conversationId) return catalog;
  return replaceModel(catalog, contextKey, {
    ...current,
    activeConversationId: conversationId,
    updatedAt: selectedAt,
  });
}

export function setCadModelConversationType(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  type: CadModelConversationType,
  updatedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  const conversation = current?.conversations[conversationId];
  if (!current || !conversation || conversation.type === type) return catalog;
  return replaceModel(catalog, contextKey, {
    ...current,
    conversations: {
      ...current.conversations,
      [conversationId]: { ...conversation, type, updatedAt },
    },
    updatedAt,
  });
}

export function archiveCadModelConversation(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  archivedAt: string
): CadModelConversationArchive {
  const current = catalog.models[contextKey];
  const conversation = current?.conversations[conversationId];
  if (!current || !conversation) return { status: 'missing', catalog };
  if (conversation.archivedAt) return { status: 'unchanged', catalog };
  if (isCadRunInProgress(current) && current.run.conversationId === conversationId) {
    return { status: 'run-in-progress', catalog };
  }

  const remaining = Object.values(current.conversations)
    .filter((candidate) => candidate.id !== conversationId && !candidate.archivedAt)
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
  const nextConversationId = remaining[0]?.id;
  if (!nextConversationId) return { status: 'last-active-conversation', catalog };

  return {
    status: 'archived',
    catalog: replaceModel(catalog, contextKey, {
      ...current,
      conversations: {
        ...current.conversations,
        [conversationId]: { ...conversation, archivedAt, updatedAt: archivedAt },
      },
      ...(current.activeConversationId === conversationId
        ? { activeConversationId: nextConversationId }
        : {}),
      ...(current.editingConversationId === conversationId
        ? { editingConversationId: nextConversationId }
        : {}),
      updatedAt: archivedAt,
    }),
  };
}

export function restoreCadModelConversation(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  restoredAt: string
): CadModelConversationArchive {
  const current = catalog.models[contextKey];
  const conversation = current?.conversations[conversationId];
  if (!current || !conversation) return { status: 'missing', catalog };
  if (!conversation.archivedAt) return { status: 'unchanged', catalog };

  return {
    status: 'restored',
    catalog: replaceModel(catalog, contextKey, {
      ...current,
      conversations: {
        ...current.conversations,
        [conversationId]: { ...conversation, archivedAt: undefined, updatedAt: restoredAt },
      },
      activeConversationId: conversationId,
      updatedAt: restoredAt,
    }),
  };
}

const MAX_PERSISTED_TURN_DURATIONS = 200;

export function recordCadConversationTurnDuration(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  turnId: string,
  durationMs: number,
  updatedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  const conversation = current?.conversations[conversationId];
  if (!current || !conversation) return catalog;

  const duration = Math.max(0, Math.round(durationMs));
  if (conversation.turnDurationsMs?.[turnId] === duration) return catalog;

  const entries = Object.entries({
    ...conversation.turnDurationsMs,
    [turnId]: duration,
  }).slice(-MAX_PERSISTED_TURN_DURATIONS);

  return replaceModel(catalog, contextKey, {
    ...current,
    conversations: {
      ...current.conversations,
      [conversationId]: {
        ...conversation,
        turnDurationsMs: Object.fromEntries(entries),
        updatedAt,
      },
    },
    updatedAt,
  });
}

export function removeCadModelConversation(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  updatedAt: string
): CadModelConversationRemoval {
  const current = catalog.models[contextKey];
  if (!current?.conversations[conversationId]) return { status: 'missing', catalog };
  const activeConversations = Object.values(current.conversations).filter(
    (conversation) => !conversation.archivedAt
  );
  if (!current.conversations[conversationId].archivedAt && activeConversations.length === 1) {
    return { status: 'last-conversation', catalog };
  }
  if (isCadRunInProgress(current) && current.run.conversationId === conversationId) {
    return { status: 'run-in-progress', catalog };
  }

  const conversations = { ...current.conversations };
  delete conversations[conversationId];
  const activeConversationId =
    current.activeConversationId === conversationId
      ? Object.values(conversations)
          .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
          .find((conversation) => !conversation.archivedAt)?.id
      : current.activeConversationId;

  return {
    status: 'removed',
    catalog: replaceModel(catalog, contextKey, {
      ...current,
      conversations,
      ...(activeConversationId ? { activeConversationId } : {}),
      ...(current.editingConversationId === conversationId
        ? { editingConversationId: activeConversationId }
        : {}),
      updatedAt,
    }),
  };
}

export function switchCadEditingConversation(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  updatedAt: string
): CadEditingConversationSwitch {
  const current = catalog.models[contextKey];
  const conversation = current?.conversations[conversationId];
  if (!current || !conversation) return { status: 'missing', catalog, stale: false };
  if (isCadRunInProgress(current)) {
    return { status: 'run-in-progress', catalog, stale: false };
  }
  const stale = conversation.lastContextRevisionId !== current.revisionId;
  if (
    current.editingConversationId === conversationId &&
    current.activeConversationId === conversationId
  ) {
    return { status: 'unchanged', catalog, stale };
  }
  return {
    status: 'updated',
    stale,
    catalog: replaceModel(catalog, contextKey, {
      ...current,
      activeConversationId: conversationId,
      editingConversationId: conversationId,
      updatedAt,
    }),
  };
}

export function cadEditAvailability(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string
): CadEditAvailability {
  const current = catalog.models[contextKey];
  if (!current) return { allowed: false, reason: 'missing-model' };
  if (!current.conversations[conversationId]) return { allowed: false, reason: 'missing-model' };
  if (isCadRunInProgress(current)) return { allowed: false, reason: 'run-in-progress' };
  return { allowed: true };
}

export function markCadConversationContextCurrent(
  catalog: CadModelCatalog,
  contextKey: string,
  conversationId: string,
  updatedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  const conversation = current?.conversations[conversationId];
  if (!current || !conversation) return catalog;
  return replaceModel(catalog, contextKey, {
    ...current,
    conversations: {
      ...current.conversations,
      [conversationId]: {
        ...conversation,
        ...(current.revisionId ? { lastContextRevisionId: current.revisionId } : {}),
        updatedAt,
      },
    },
    updatedAt,
  });
}

export function startCadRun(
  catalog: CadModelCatalog,
  identity: CadModelIdentity,
  run: {
    id: string;
    conversationId: string;
    prompt: string;
    startedAt: string;
    lastGood?: CadLastGoodSnapshot;
  }
): CadModelCatalog {
  const current = modelRecord(catalog.models[identity.contextKey], identity, run.startedAt);
  if (isCadRunInProgress(current)) return catalog;
  const conversation = current.conversations[run.conversationId];
  if (!conversation) return catalog;
  return {
    ...catalog,
    activeModelKey: identity.contextKey,
    models: {
      ...catalog.models,
      [identity.contextKey]: {
        ...current,
        ...(run.lastGood ? { lastGood: run.lastGood } : {}),
        conversations: {
          ...current.conversations,
          [run.conversationId]: {
            ...conversation,
            ...(current.revisionId ? { lastContextRevisionId: current.revisionId } : {}),
            updatedAt: run.startedAt,
          },
        },
        run: {
          id: run.id,
          conversationId: run.conversationId,
          origin: 'agent',
          status: 'generating',
          prompt: run.prompt,
          startedAt: run.startedAt,
        },
        updatedAt: run.startedAt,
      },
    },
  };
}

export function startCadSourceRun(
  catalog: CadModelCatalog,
  identity: CadModelIdentity,
  run: {
    id: string;
    startedAt: string;
    lastGood?: CadLastGoodSnapshot;
  }
): CadModelCatalog {
  const current = modelRecord(catalog.models[identity.contextKey], identity, run.startedAt);
  if (isCadRunInProgress(current)) return catalog;
  return {
    ...catalog,
    activeModelKey: identity.contextKey,
    models: {
      ...catalog.models,
      [identity.contextKey]: {
        ...current,
        ...(run.lastGood ? { lastGood: run.lastGood } : {}),
        run: {
          id: run.id,
          origin: 'source',
          status: 'generating',
          prompt: 'Direct source edit',
          startedAt: run.startedAt,
        },
        updatedAt: run.startedAt,
      },
    },
  };
}

export function finishCadRun(
  catalog: CadModelCatalog,
  contextKey: string,
  status: Exclude<CadRunStatus, 'ready' | 'generating' | 'validating' | 'restored'>,
  endedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current || current.run.status !== 'generating') return catalog;
  return replaceModel(catalog, contextKey, {
    ...current,
    run: { ...current.run, status, endedAt },
    lastGood:
      status === 'completed'
        ? {
            modelPath: current.modelPath,
            ...(current.sourcePath ? { sourcePath: current.sourcePath } : {}),
            recordedAt: endedAt,
            validationStatus: 'unknown',
            ...(current.revisionId ? { revisionId: current.revisionId } : {}),
          }
        : current.lastGood,
    updatedAt: endedAt,
  });
}

/**
 * Retires a persisted in-progress run after renderer restart without restoring
 * its old backup over the current canonical artifact on disk.
 */
export function interruptRecoveredCadRun(
  catalog: CadModelCatalog,
  contextKey: string,
  runId: string,
  interruptedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (
    !current ||
    current.run.id !== runId ||
    (current.run.status !== 'generating' && current.run.status !== 'validating')
  ) {
    return catalog;
  }
  return replaceModel(catalog, contextKey, {
    ...current,
    run: { ...current.run, status: 'interrupted', endedAt: interruptedAt },
    updatedAt: interruptedAt,
  });
}

export function beginCadValidation(catalog: CadModelCatalog, contextKey: string): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current || current.run.status !== 'generating') return catalog;
  return replaceModel(catalog, contextKey, {
    ...current,
    run: { ...current.run, status: 'validating' },
  });
}

export function finishCadValidation(
  catalog: CadModelCatalog,
  contextKey: string,
  result:
    | {
        success: true;
        artifact: CadArtifactIdentity;
        facts: {
          occurrenceCount?: number;
          faceCount?: number;
          size?: [number, number, number];
        };
      }
    | { success: false; error: string },
  checkedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current || current.run.status !== 'validating') return catalog;
  const revisionId = result.success ? result.artifact.revisionId : undefined;
  const runConversation = current.run.conversationId
    ? current.conversations[current.run.conversationId]
    : undefined;
  const canonicalCurrent = result.success ? withoutCadSourceProvenance(current) : current;
  return replaceModel(catalog, contextKey, {
    ...canonicalCurrent,
    ...(revisionId ? { revisionId } : {}),
    ...(result.success
      ? {
          modelPath: result.artifact.modelPath,
          modelHash: result.artifact.modelHash,
          artifacts: cadCoreArtifacts(result.artifact.modelPath, result.artifact.sourcePath),
          ...(result.artifact.sourcePath ? { sourcePath: result.artifact.sourcePath } : {}),
          ...(result.artifact.sourceHash ? { sourceHash: result.artifact.sourceHash } : {}),
        }
      : {}),
    conversations:
      revisionId && runConversation && current.run.conversationId
        ? {
            ...current.conversations,
            [current.run.conversationId]: {
              ...runConversation,
              lastContextRevisionId: revisionId,
              updatedAt: checkedAt,
            },
          }
        : current.conversations,
    run: {
      ...current.run,
      status: result.success ? 'completed' : 'failed',
      endedAt: checkedAt,
      validation: result.success
        ? { status: 'passed', checkedAt, facts: result.facts }
        : { status: 'failed', checkedAt, error: result.error },
    },
    lastGood: result.success
      ? {
          modelPath: result.artifact.modelPath,
          ...(result.artifact.sourcePath ? { sourcePath: result.artifact.sourcePath } : {}),
          recordedAt: checkedAt,
          validationStatus: 'passed',
          ...(revisionId ? { revisionId } : {}),
          modelHash: result.artifact.modelHash,
          ...(result.artifact.sourceHash ? { sourceHash: result.artifact.sourceHash } : {}),
        }
      : current.lastGood,
    updatedAt: checkedAt,
  });
}

export function reconcileCadArtifactFromDisk(
  catalog: CadModelCatalog,
  contextKey: string,
  artifact: CadArtifactIdentity,
  facts: {
    occurrenceCount?: number;
    faceCount?: number;
    size?: [number, number, number];
  },
  checkedAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current || isCadRunInProgress(current)) return catalog;
  // A successful disk inspection is the provenance authority. If it does not
  // report a source, an older same-stem/catalog guess must not survive merely
  // because the accepted STEP path stayed the same.
  const linkedSourcePath = artifact.sourcePath;
  const unchanged =
    current.revisionId === artifact.revisionId &&
    current.modelHash === artifact.modelHash &&
    current.sourcePath === linkedSourcePath &&
    current.sourceHash === artifact.sourceHash;
  if (unchanged && current.run.validation?.status === 'passed') return catalog;
  const canonicalCurrent = withoutCadSourceProvenance(current);
  return replaceModel(catalog, contextKey, {
    ...canonicalCurrent,
    revisionId: artifact.revisionId,
    modelPath: artifact.modelPath,
    modelHash: artifact.modelHash,
    artifacts: cadCoreArtifacts(artifact.modelPath, linkedSourcePath),
    ...(linkedSourcePath ? { sourcePath: linkedSourcePath } : {}),
    ...(artifact.sourceHash ? { sourceHash: artifact.sourceHash } : {}),
    run: {
      ...current.run,
      status: current.run.status === 'completed' ? 'completed' : 'restored',
      endedAt: checkedAt,
      validation: { status: 'passed', checkedAt, facts },
    },
    lastGood: {
      modelPath: artifact.modelPath,
      ...(linkedSourcePath ? { sourcePath: linkedSourcePath } : {}),
      recordedAt: checkedAt,
      validationStatus: 'passed',
      revisionId: artifact.revisionId,
      modelHash: artifact.modelHash,
      ...(artifact.sourceHash ? { sourceHash: artifact.sourceHash } : {}),
    },
    updatedAt: checkedAt,
  });
}

export function restoreCadRun(
  catalog: CadModelCatalog,
  contextKey: string,
  restoredAt: string
): CadModelCatalog {
  const current = catalog.models[contextKey];
  if (!current?.lastGood) return catalog;
  return replaceModel(catalog, contextKey, {
    ...current,
    ...(current.lastGood.revisionId ? { revisionId: current.lastGood.revisionId } : {}),
    run: {
      ...current.run,
      status: 'restored',
      endedAt: restoredAt,
    },
    updatedAt: restoredAt,
  });
}

function modelRecord(
  existing: CadModelRecord | undefined,
  identity: CadModelIdentity,
  now: string
): CadModelRecord {
  const revisionId =
    existing?.revisionId ??
    (existing?.lastGood?.validationStatus === 'passed'
      ? `legacy:${existing.lastGood.recordedAt}`
      : undefined);
  // Once validation records canonical provenance, a same-stem fallback from a
  // newly opened tab must never replace it. A successful validation is the
  // authority allowed to move an existing model to different paths.
  const modelPath = existing?.modelPath ?? identity.modelPath;
  const sourcePath = existing?.sourcePath ?? identity.sourcePath;
  const artifacts = cadCoreArtifacts(modelPath, sourcePath);
  if (
    existing &&
    existing.modelPath === modelPath &&
    existing.sourcePath === sourcePath &&
    existing.revisionId === revisionId &&
    sameArtifacts(existing.artifacts, artifacts)
  ) {
    return existing;
  }
  return {
    ...existing,
    contextKey: identity.contextKey,
    modelPath,
    ...(sourcePath ? { sourcePath } : {}),
    artifacts,
    ...(revisionId ? { revisionId } : {}),
    ...(existing?.lastGood
      ? {
          lastGood: {
            ...existing.lastGood,
            ...(revisionId ? { revisionId } : {}),
          },
        }
      : {}),
    conversations: existing?.conversations ?? {},
    run: existing?.run ?? { status: 'ready' },
    updatedAt: now,
  };
}

function replaceModel(
  catalog: CadModelCatalog,
  contextKey: string,
  model: CadModelRecord
): CadModelCatalog {
  return { ...catalog, models: { ...catalog.models, [contextKey]: model } };
}

function isCadRunInProgress(model: CadModelRecord): boolean {
  return model.run.status === 'generating' || model.run.status === 'validating';
}

function cadCoreArtifacts(modelPath: string, sourcePath?: string): CadModelRecord['artifacts'] {
  return [
    ...(sourcePath ? [{ path: sourcePath, role: 'source' as const }] : []),
    { path: modelPath, role: 'model' as const },
  ];
}

function withoutCadSourceProvenance(model: CadModelRecord): CadModelRecord {
  const { sourcePath: _sourcePath, sourceHash: _sourceHash, ...rest } = model;
  return rest;
}

function sameArtifacts(
  left: CadModelRecord['artifacts'],
  right: CadModelRecord['artifacts']
): boolean {
  return (
    left.length === right.length &&
    left.every((artifact, index) => {
      const other = right[index];
      return artifact.path === other?.path && artifact.role === other.role;
    })
  );
}

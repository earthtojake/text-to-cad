import { describe, expect, it } from 'vitest';
import type { CadModelCatalog } from '@core/features/cad/contributions/mementos';
import { cadModelCatalogSchema } from '@core/features/cad/contributions/mementos';
import {
  archiveCadModelConversation,
  beginCadValidation,
  cadEditAvailability,
  ensureCadModel,
  finishCadRun,
  finishCadValidation,
  interruptRecoveredCadRun,
  markCadConversationContextCurrent,
  reconcileCadArtifactFromDisk,
  reconcileCadModelConversations,
  recordCadConversationTurnDuration,
  registerCadModelConversation,
  removeCadModelConversation,
  restoreCadModelConversation,
  restoreCadRun,
  selectCadModelConversation,
  setCadModelConversationType,
  startCadRun,
  startCadSourceRun,
  switchCadEditingConversation,
} from './cad-model-state';

const emptyCatalog: CadModelCatalog = { version: '3', models: {} };
const identity = {
  contextKey: 'cad-model:examples/plate',
  modelPath: 'examples/plate.step',
  sourcePath: 'examples/plate.step.py',
};
const openedAt = '2026-08-24T10:00:00.000Z';

function withModel(): CadModelCatalog {
  return ensureCadModel(emptyCatalog, identity, openedAt);
}

function withConversation(
  id = 'design-1',
  type: 'design' | 'analysis' | 'manufacturing' | 'review' | 'custom' = 'design'
): CadModelCatalog {
  return registerCadModelConversation(withModel(), identity.contextKey, {
    id,
    type,
    createdAt: openedAt,
  });
}

describe('CAD model catalog', () => {
  it('persists bounded per-conversation turn durations without rewriting identical values', () => {
    const catalog = withConversation();
    const recorded = recordCadConversationTurnDuration(
      catalog,
      identity.contextKey,
      'design-1',
      'design-1:turn:4',
      74_050.4,
      '2026-08-25T23:00:00.000Z'
    );

    expect(recorded.models[identity.contextKey]?.conversations['design-1']).toMatchObject({
      turnDurationsMs: { 'design-1:turn:4': 74_050 },
    });
    expect(
      recordCadConversationTurnDuration(
        recorded,
        identity.contextKey,
        'design-1',
        'design-1:turn:4',
        74_050,
        '2026-08-25T23:01:00.000Z'
      )
    ).toBe(recorded);
  });

  it('records one model identity with its source and generated artifact', () => {
    const next = withModel();

    expect(next.activeModelKey).toBe(identity.contextKey);
    expect(next.models[identity.contextKey]).toMatchObject({
      ...identity,
      conversations: {},
      run: { status: 'ready' },
      artifacts: [
        { path: identity.sourcePath, role: 'source' },
        { path: identity.modelPath, role: 'model' },
      ],
    });
  });

  it('migrates the existing model conversation to default Design without losing its id', () => {
    const migrated = cadModelCatalogSchema.safeParse({
      version: '1',
      activeModelKey: identity.contextKey,
      models: {
        [identity.contextKey]: {
          ...identity,
          conversationId: 'legacy-conversation',
          artifacts: [
            { path: identity.sourcePath, role: 'source' },
            { path: identity.modelPath, role: 'model' },
          ],
          run: { id: 'revision-1', status: 'completed' },
          updatedAt: openedAt,
        },
      },
    });

    expect(migrated.status).toBe('ok');
    if (migrated.status !== 'ok') return;
    expect(migrated.data.version).toBe('3');
    expect(migrated.data.models[identity.contextKey]).toMatchObject({
      activeConversationId: 'legacy-conversation',
      editingConversationId: 'legacy-conversation',
      conversations: {
        'legacy-conversation': { id: 'legacy-conversation', type: 'design' },
      },
    });
  });

  it('assigns a stable legacy revision to a restored validated snapshot', () => {
    const recordedAt = '2026-08-24T09:00:00.000Z';
    const migrated = cadModelCatalogSchema.safeParse({
      version: '1',
      models: {
        [identity.contextKey]: {
          ...identity,
          conversationId: 'legacy-conversation',
          artifacts: [{ path: identity.modelPath, role: 'model' }],
          run: { id: 'failed-run', status: 'restored' },
          lastGood: {
            modelPath: identity.modelPath,
            recordedAt,
            validationStatus: 'passed',
          },
          updatedAt: openedAt,
        },
      },
    });

    expect(migrated.status).toBe('ok');
    if (migrated.status !== 'ok') return;
    expect(migrated.data.models[identity.contextKey]).toMatchObject({
      revisionId: `legacy:${recordedAt}`,
      lastGood: { revisionId: `legacy:${recordedAt}` },
    });
  });

  it('replaces stale session revision metadata with the validated on-disk hashes after restart', () => {
    const stale = {
      ...withConversation(),
      models: {
        [identity.contextKey]: {
          ...withConversation().models[identity.contextKey]!,
          revisionId: 'session-run-id',
          run: { status: 'interrupted' as const },
        },
      },
    };
    const reconciled = reconcileCadArtifactFromDisk(
      stale,
      identity.contextKey,
      {
        revisionId: 'sha256:disk-revision',
        modelPath: identity.modelPath,
        modelHash: 'disk-model-hash',
        sourcePath: identity.sourcePath,
        sourceHash: 'disk-source-hash',
      },
      { occurrenceCount: 4, faceCount: 24 },
      '2026-08-24T11:00:00.000Z'
    );

    expect(reconciled.models[identity.contextKey]).toMatchObject({
      revisionId: 'sha256:disk-revision',
      modelHash: 'disk-model-hash',
      sourceHash: 'disk-source-hash',
      run: { status: 'restored', validation: { status: 'passed' } },
      lastGood: { revisionId: 'sha256:disk-revision' },
    });
  });

  it('keeps catalog-known canonical paths when a tab later supplies same-stem fallbacks', () => {
    const canonical = reconcileCadArtifactFromDisk(
      withModel(),
      identity.contextKey,
      {
        revisionId: 'sha256:canonical',
        modelPath: 'build/accepted.step',
        modelHash: 'accepted-model-hash',
        sourcePath: 'generators/rebuild.py',
        sourceHash: 'accepted-source-hash',
      },
      { faceCount: 12 },
      '2026-08-24T10:30:00.000Z'
    );

    const reopened = ensureCadModel(canonical, identity, '2026-08-24T10:31:00.000Z');

    expect(reopened.models[identity.contextKey]).toMatchObject({
      modelPath: 'build/accepted.step',
      sourcePath: 'generators/rebuild.py',
      artifacts: [
        { path: 'generators/rebuild.py', role: 'source' },
        { path: 'build/accepted.step', role: 'model' },
      ],
    });
  });

  it('refreshes core artifact links and clears stale source provenance from imported STEP files', () => {
    const generated = reconcileCadArtifactFromDisk(
      withModel(),
      identity.contextKey,
      {
        revisionId: 'sha256:generated',
        modelPath: 'build/generated.step',
        modelHash: 'generated-model-hash',
        sourcePath: 'generators/generated.py',
        sourceHash: 'generated-source-hash',
      },
      {},
      '2026-08-24T10:40:00.000Z'
    );
    const imported = reconcileCadArtifactFromDisk(
      generated,
      identity.contextKey,
      {
        revisionId: 'sha256:imported',
        modelPath: 'imports/vendor.step',
        modelHash: 'imported-model-hash',
      },
      {},
      '2026-08-24T10:41:00.000Z'
    );

    expect(imported.models[identity.contextKey]).toMatchObject({
      modelPath: 'imports/vendor.step',
      artifacts: [{ path: 'imports/vendor.step', role: 'model' }],
    });
    expect(imported.models[identity.contextKey]?.sourcePath).toBeUndefined();
    expect(imported.models[identity.contextKey]?.sourceHash).toBeUndefined();
  });

  it('clears stale source provenance when the current same-STEP inspection reports none', () => {
    const linked = {
      ...withModel(),
      models: {
        [identity.contextKey]: {
          ...withModel().models[identity.contextKey]!,
          sourceHash: 'stale-source-hash',
          run: { status: 'interrupted' as const },
        },
      },
    };

    const reconciled = reconcileCadArtifactFromDisk(
      linked,
      identity.contextKey,
      {
        revisionId: 'sha256:accepted-step',
        modelPath: identity.modelPath,
        modelHash: 'accepted-step-hash',
      },
      { faceCount: 8 },
      '2026-08-24T10:42:00.000Z'
    );

    expect(reconciled.models[identity.contextKey]).toMatchObject({
      modelPath: identity.modelPath,
      artifacts: [{ path: identity.modelPath, role: 'model' }],
      run: { status: 'restored', validation: { status: 'passed' } },
    });
    expect(reconciled.models[identity.contextKey]?.sourcePath).toBeUndefined();
    expect(reconciled.models[identity.contextKey]?.sourceHash).toBeUndefined();
    expect(reconciled.models[identity.contextKey]?.lastGood?.sourcePath).toBeUndefined();
    expect(reconciled.models[identity.contextKey]?.lastGood?.sourceHash).toBeUndefined();
  });

  it('preserves independent active and editing conversations across serialization', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'analysis-1',
      type: 'analysis',
      createdAt: openedAt,
    });
    catalog = selectCadModelConversation(catalog, identity.contextKey, 'analysis-1', openedAt);
    const parsed = cadModelCatalogSchema.parseJson(cadModelCatalogSchema.serialize(catalog));

    expect(parsed?.models[identity.contextKey]).toMatchObject({
      activeConversationId: 'analysis-1',
      editingConversationId: 'design-1',
      conversations: {
        'design-1': { type: 'design' },
        'analysis-1': { type: 'analysis' },
      },
    });
  });

  it('archives only the chat metadata and preserves the model and transcript identity', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: '2026-08-24T10:01:00.000Z',
    });
    const archivedAt = '2026-08-26T10:00:00.000Z';
    const result = archiveCadModelConversation(
      catalog,
      identity.contextKey,
      'review-1',
      archivedAt
    );

    expect(result.status).toBe('archived');
    expect(result.catalog.models[identity.contextKey]).toMatchObject({
      modelPath: identity.modelPath,
      sourcePath: identity.sourcePath,
      activeConversationId: 'design-1',
      conversations: {
        'design-1': { id: 'design-1' },
        'review-1': { id: 'review-1', archivedAt },
      },
    });
    expect(
      cadModelCatalogSchema.parseJson(cadModelCatalogSchema.serialize(result.catalog))
    ).toEqual(result.catalog);
  });

  it('restores and selects an archived chat without changing model artifacts', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: '2026-08-24T10:01:00.000Z',
    });
    const archived = archiveCadModelConversation(
      catalog,
      identity.contextKey,
      'review-1',
      '2026-08-26T10:00:00.000Z'
    );
    const restored = restoreCadModelConversation(
      archived.catalog,
      identity.contextKey,
      'review-1',
      '2026-08-26T10:05:00.000Z'
    );

    expect(restored.status).toBe('restored');
    expect(restored.catalog.models[identity.contextKey]).toMatchObject({
      modelPath: identity.modelPath,
      artifacts: [
        { path: identity.sourcePath, role: 'source' },
        { path: identity.modelPath, role: 'model' },
      ],
      activeConversationId: 'review-1',
      conversations: { 'review-1': { archivedAt: undefined } },
    });
  });

  it('protects the last active chat and an in-progress revision from archival', () => {
    expect(
      archiveCadModelConversation(withConversation(), identity.contextKey, 'design-1', openedAt)
        .status
    ).toBe('last-active-conversation');

    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: '2026-08-24T10:01:00.000Z',
    });
    catalog = startCadRun(catalog, identity, {
      id: 'run-1',
      conversationId: 'review-1',
      prompt: 'Revise it',
      startedAt: openedAt,
    });

    expect(
      archiveCadModelConversation(catalog, identity.contextKey, 'review-1', openedAt).status
    ).toBe('run-in-progress');
  });

  it('reconciles several persisted ACP histories without crossing model boundaries', () => {
    const next = reconcileCadModelConversations(
      withModel(),
      identity.contextKey,
      ['conversation-a', 'conversation-b'],
      openedAt
    );

    expect(next.models[identity.contextKey]?.conversations).toMatchObject({
      'conversation-a': { type: 'design' },
      'conversation-b': { type: 'custom' },
    });
    expect(next.models[identity.contextKey]?.editingConversationId).toBe('conversation-a');
    expect(
      reconcileCadModelConversations(next, 'cad-model:examples/other', ['other'], openedAt)
    ).toBe(next);
  });

  it('switches, renames by external history id, and changes thread type independently', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: openedAt,
    });
    catalog = selectCadModelConversation(catalog, identity.contextKey, 'design-1', openedAt);
    catalog = setCadModelConversationType(
      catalog,
      identity.contextKey,
      'review-1',
      'manufacturing',
      openedAt
    );

    expect(catalog.models[identity.contextKey]).toMatchObject({
      activeConversationId: 'design-1',
      editingConversationId: 'design-1',
      conversations: { 'review-1': { type: 'manufacturing' } },
    });
  });

  it('deletes a discussion chat and selects the oldest remaining history', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'analysis-1',
      type: 'analysis',
      createdAt: '2026-08-24T10:01:00.000Z',
    });

    const result = removeCadModelConversation(
      catalog,
      identity.contextKey,
      'analysis-1',
      '2026-08-24T10:02:00.000Z'
    );

    expect(result.status).toBe('removed');
    expect(result.catalog.models[identity.contextKey]).toMatchObject({
      activeConversationId: 'design-1',
      editingConversationId: 'design-1',
      conversations: { 'design-1': { type: 'design' } },
    });
    expect(result.catalog.models[identity.contextKey]?.conversations['analysis-1']).toBeUndefined();
  });

  it('protects the last chat but lets any inactive chat be deleted', () => {
    const onlyConversation = withConversation();
    expect(
      removeCadModelConversation(onlyConversation, identity.contextKey, 'design-1', openedAt).status
    ).toBe('last-conversation');

    const withAnalysis = registerCadModelConversation(onlyConversation, identity.contextKey, {
      id: 'analysis-1',
      type: 'analysis',
      createdAt: openedAt,
    });
    const removed = removeCadModelConversation(
      withAnalysis,
      identity.contextKey,
      'design-1',
      openedAt
    );
    expect(removed.status).toBe('removed');
    expect(removed.catalog.models[identity.contextKey]?.editingConversationId).toBe('analysis-1');
  });

  it('warns when an editing handoff conversation has stale model context', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: openedAt,
    });
    catalog = {
      ...catalog,
      models: {
        ...catalog.models,
        [identity.contextKey]: {
          ...catalog.models[identity.contextKey]!,
          revisionId: 'revision-2',
        },
      },
    };

    const switched = switchCadEditingConversation(
      catalog,
      identity.contextKey,
      'review-1',
      openedAt
    );

    expect(switched.status).toBe('updated');
    expect(switched.stale).toBe(true);
    expect(switched.catalog.models[identity.contextKey]).toMatchObject({
      activeConversationId: 'review-1',
      editingConversationId: 'review-1',
    });
  });

  it('lets every attached conversation start a model mutation', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'analysis-1',
      type: 'analysis',
      createdAt: openedAt,
    });
    expect(cadEditAvailability(catalog, identity.contextKey, 'analysis-1')).toEqual({
      allowed: true,
    });

    const started = startCadRun(catalog, identity, {
      id: 'run-1',
      conversationId: 'analysis-1',
      prompt: 'Change the thickness',
      startedAt: openedAt,
    });
    expect(started.models[identity.contextKey]?.run).toMatchObject({
      id: 'run-1',
      conversationId: 'analysis-1',
      status: 'generating',
    });
  });

  it('prevents an editing handoff and a second run while geometry is changing', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: openedAt,
    });
    catalog = selectCadModelConversation(catalog, identity.contextKey, 'design-1', openedAt);
    const running = startCadRun(catalog, identity, {
      id: 'run-1',
      conversationId: 'design-1',
      prompt: 'Make it thinner',
      startedAt: openedAt,
    });

    expect(
      switchCadEditingConversation(running, identity.contextKey, 'review-1', openedAt).status
    ).toBe('run-in-progress');
    expect(
      startCadRun(running, identity, {
        id: 'run-2',
        conversationId: 'design-1',
        prompt: 'Also add a hole',
        startedAt: openedAt,
      })
    ).toBe(running);
  });

  it('allows different CAD models to generate at the same time', () => {
    const bracketIdentity = {
      contextKey: 'cad-model:examples/bracket',
      modelPath: 'examples/bracket.step',
      sourcePath: 'examples/bracket.step.py',
    };
    let catalog = withConversation('plate-design');
    catalog = ensureCadModel(catalog, bracketIdentity, openedAt);
    catalog = registerCadModelConversation(catalog, bracketIdentity.contextKey, {
      id: 'bracket-design',
      type: 'design',
      createdAt: openedAt,
    });

    catalog = startCadRun(catalog, identity, {
      id: 'plate-run',
      conversationId: 'plate-design',
      prompt: 'Make the plate thinner',
      startedAt: openedAt,
    });
    catalog = startCadRun(catalog, bracketIdentity, {
      id: 'bracket-run',
      conversationId: 'bracket-design',
      prompt: 'Add a mounting hole',
      startedAt: openedAt,
    });

    expect(catalog.models[identity.contextKey]?.run).toMatchObject({
      id: 'plate-run',
      status: 'generating',
    });
    expect(catalog.models[bracketIdentity.contextKey]?.run).toMatchObject({
      id: 'bracket-run',
      status: 'generating',
    });
  });

  it('records the editing conversation and advances revision only after validation passes', () => {
    const prepared = startCadRun(withConversation(), identity, {
      id: 'run-1',
      conversationId: 'design-1',
      prompt: 'Make it thinner',
      startedAt: openedAt,
    });
    const validating = beginCadValidation(prepared, identity.contextKey);
    const completed = finishCadValidation(
      validating,
      identity.contextKey,
      {
        success: true,
        artifact: {
          revisionId: 'sha256:revision-1',
          modelPath: identity.modelPath,
          modelHash: 'model-hash-1',
          sourcePath: identity.sourcePath,
          sourceHash: 'source-hash-1',
        },
        facts: { occurrenceCount: 1, faceCount: 6, size: [40, 30, 10] },
      },
      '2026-08-24T10:01:00.000Z'
    );

    expect(completed.models[identity.contextKey]).toMatchObject({
      revisionId: 'sha256:revision-1',
      modelHash: 'model-hash-1',
      sourceHash: 'source-hash-1',
      run: {
        id: 'run-1',
        conversationId: 'design-1',
        status: 'completed',
        validation: { status: 'passed', facts: { faceCount: 6 } },
      },
      conversations: { 'design-1': { lastContextRevisionId: 'sha256:revision-1' } },
      lastGood: {
        revisionId: 'sha256:revision-1',
        validationStatus: 'passed',
        modelHash: 'model-hash-1',
        sourceHash: 'source-hash-1',
      },
    });
  });

  it('keeps the prior revision and recovery snapshot when validation fails', () => {
    let catalog = withConversation();
    catalog = {
      ...catalog,
      models: {
        ...catalog.models,
        [identity.contextKey]: {
          ...catalog.models[identity.contextKey]!,
          revisionId: 'revision-0',
        },
      },
    };
    const prepared = startCadRun(catalog, identity, {
      id: 'run-1',
      conversationId: 'design-1',
      prompt: 'Make it thinner',
      startedAt: openedAt,
      lastGood: {
        modelPath: identity.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        recordedAt: openedAt,
        validationStatus: 'passed',
        revisionId: 'revision-0',
      },
    });
    const failed = finishCadValidation(
      beginCadValidation(prepared, identity.contextKey),
      identity.contextKey,
      { success: false, error: 'Geometry validation found 1 failing occurrence.' },
      '2026-08-24T10:01:00.000Z'
    );

    expect(failed.models[identity.contextKey]).toMatchObject({
      revisionId: 'revision-0',
      run: { status: 'failed', validation: { status: 'failed' } },
      lastGood: { revisionId: 'revision-0' },
    });
  });

  it('locks the model while direct source edits rebuild without borrowing a chat lease', () => {
    const prepared = startCadSourceRun(withConversation(), identity, {
      id: 'source-run-1',
      startedAt: openedAt,
      lastGood: {
        modelPath: identity.modelPath,
        backupPath: '.hardcore/last-good/plate-source-run-1.step',
        recordedAt: openedAt,
        validationStatus: 'passed',
        revisionId: 'revision-0',
      },
    });

    expect(prepared.models[identity.contextKey]?.run).toMatchObject({
      id: 'source-run-1',
      origin: 'source',
      status: 'generating',
    });
    expect(prepared.models[identity.contextKey]?.run.conversationId).toBeUndefined();
    expect(cadEditAvailability(prepared, identity.contextKey, 'design-1')).toEqual({
      allowed: false,
      reason: 'run-in-progress',
    });
  });

  it('classifies a stale generating run as interrupted after restart', () => {
    const prepared = startCadRun(withConversation(), identity, {
      id: 'run-1',
      conversationId: 'design-1',
      prompt: 'Make it thinner',
      startedAt: openedAt,
    });
    const recovered = finishCadRun(
      prepared,
      identity.contextKey,
      'interrupted',
      '2026-08-24T10:01:00.000Z'
    );

    expect(recovered.models[identity.contextKey]?.run).toMatchObject({
      id: 'run-1',
      conversationId: 'design-1',
      status: 'interrupted',
    });
  });

  it('retires a recovered source validation without restoring stale session files', () => {
    const generating = startCadSourceRun(withConversation(), identity, {
      id: 'source-run-1',
      startedAt: openedAt,
    });
    const validating = beginCadValidation(generating, identity.contextKey);
    const recovered = interruptRecoveredCadRun(
      validating,
      identity.contextKey,
      'source-run-1',
      '2026-08-24T10:01:00.000Z'
    );

    expect(recovered.models[identity.contextKey]).toMatchObject({
      modelPath: identity.modelPath,
      sourcePath: identity.sourcePath,
      run: {
        id: 'source-run-1',
        origin: 'source',
        status: 'interrupted',
        endedAt: '2026-08-24T10:01:00.000Z',
      },
    });
    expect(
      interruptRecoveredCadRun(
        recovered,
        identity.contextKey,
        'obsolete-source-run',
        '2026-08-24T10:02:00.000Z'
      )
    ).toBe(recovered);
  });

  it('restores the previous revision and later refreshes discussion context', () => {
    let catalog = withConversation();
    catalog = registerCadModelConversation(catalog, identity.contextKey, {
      id: 'review-1',
      type: 'review',
      createdAt: openedAt,
    });
    catalog = selectCadModelConversation(catalog, identity.contextKey, 'design-1', openedAt);
    const prepared = startCadRun(catalog, identity, {
      id: 'run-1',
      conversationId: 'design-1',
      prompt: 'Make it thinner',
      startedAt: openedAt,
      lastGood: {
        modelPath: identity.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        sourcePath: identity.sourcePath,
        sourceBackupPath: '.hardcore/last-good/plate-run-1.source.step.py',
        recordedAt: openedAt,
        validationStatus: 'passed',
        revisionId: 'revision-0',
      },
    });
    const failed = finishCadRun(prepared, identity.contextKey, 'failed', openedAt);
    let restored = restoreCadRun(failed, identity.contextKey, openedAt);
    restored = markCadConversationContextCurrent(
      restored,
      identity.contextKey,
      'review-1',
      openedAt
    );

    expect(restored.models[identity.contextKey]).toMatchObject({
      revisionId: 'revision-0',
      run: { status: 'restored' },
      conversations: { 'review-1': { lastContextRevisionId: 'revision-0' } },
    });
  });
});

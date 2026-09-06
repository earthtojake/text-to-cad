import { describe, expect, it, vi } from 'vitest';
import type { CadModelCatalog } from '@core/features/cad/contributions/mementos';
import {
  activeCadWorkbenchTarget,
  abortPreparedCadWorkbenchRun,
  cadRecoveredRunIsAbandoned,
  cadWorkbenchTurnIsComplete,
  ensureCadWorkbenchModel,
  prepareCadWorkbenchRun,
  validateCadWorkbenchArtifact,
} from './cad-workbench-lifecycle';

function emptyCatalog(): CadModelCatalog {
  return { version: '3', models: {} };
}

describe('CAD workbench lifecycle', () => {
  it('uses the explicit active artifact when several models are available', () => {
    const catalog: CadModelCatalog = {
      version: '3',
      activeModelKey: 'cad-model:models/plate',
      models: {
        'cad-model:models/plate': {
          contextKey: 'cad-model:models/plate',
          modelPath: 'models/plate.step',
          artifacts: [{ path: 'models/plate.step', role: 'model' }],
          conversations: {},
          run: { status: 'ready' },
          updatedAt: '2026-08-29T09:00:00.000Z',
        },
        'cad-model:models/bracket': {
          contextKey: 'cad-model:models/bracket',
          modelPath: 'models/bracket.step',
          sourcePath: 'recipes/bracket.py',
          artifacts: [
            { path: 'recipes/bracket.py', role: 'source' },
            { path: 'models/bracket.step', role: 'model' },
          ],
          conversations: {},
          run: { status: 'ready' },
          updatedAt: '2026-08-29T09:00:00.000Z',
        },
      },
    };

    expect(activeCadWorkbenchTarget(catalog, 'cad-model:models/bracket')).toEqual({
      status: 'ready',
      identity: {
        contextKey: 'cad-model:models/bracket',
        modelPath: 'models/bracket.step',
        sourcePath: 'recipes/bracket.py',
      },
      modelFiles: ['recipes/bracket.py', 'models/bracket.step'],
    });
  });

  it('does not redirect a stale explicit focus to a different active model', () => {
    const catalog: CadModelCatalog = {
      version: '3',
      activeModelKey: 'cad-model:models/plate',
      models: {
        'cad-model:models/plate': {
          contextKey: 'cad-model:models/plate',
          modelPath: 'models/plate.step',
          artifacts: [{ path: 'models/plate.step', role: 'model' }],
          conversations: {},
          run: { status: 'ready' },
          updatedAt: '2026-08-29T09:00:00.000Z',
        },
      },
    };

    expect(activeCadWorkbenchTarget(catalog, 'cad-model:models/deleted-bracket')).toEqual({
      status: 'missing',
      contextKey: 'cad-model:models/deleted-bracket',
    });
  });

  it('registers background panes without stealing the last focused artifact', () => {
    const plate = {
      contextKey: 'cad-model:models/plate',
      modelPath: 'models/plate.step',
    };
    const bracket = {
      contextKey: 'cad-model:models/bracket',
      modelPath: 'models/bracket.step',
    };
    const withPlate = ensureCadWorkbenchModel(
      emptyCatalog(),
      plate,
      true,
      '2026-08-29T09:00:00.000Z'
    );
    const backgroundBracket = ensureCadWorkbenchModel(
      withPlate,
      bracket,
      false,
      '2026-08-29T09:01:00.000Z'
    );

    expect(backgroundBracket.activeModelKey).toBe(plate.contextKey);
    expect(backgroundBracket.models[bracket.contextKey]?.modelPath).toBe(bracket.modelPath);

    const focusedBracket = ensureCadWorkbenchModel(
      backgroundBracket,
      bracket,
      true,
      '2026-08-29T09:02:00.000Z'
    );
    expect(focusedBracket.activeModelKey).toBe(bracket.contextKey);
  });

  it('retires an abandoned persisted run without interrupting a loading or resumed session', () => {
    expect(
      cadRecoveredRunIsAbandoned({
        runStatus: 'generating',
        restoredRun: true,
        sessionReady: true,
        sessionWorking: false,
        sessionStatus: 'idle',
        agentStatus: 'idle',
      })
    ).toBe(true);
    expect(
      cadRecoveredRunIsAbandoned({
        runStatus: 'generating',
        restoredRun: true,
        sessionReady: false,
        sessionWorking: false,
        sessionStatus: 'idle',
        agentStatus: 'idle',
      })
    ).toBe(false);
    expect(
      cadRecoveredRunIsAbandoned({
        runStatus: 'generating',
        restoredRun: true,
        sessionReady: true,
        sessionWorking: true,
        sessionStatus: 'working',
        agentStatus: 'working',
      })
    ).toBe(false);
  });

  it('does not mistake the optimistic user item and previous completed status for a finished run', () => {
    expect(
      cadWorkbenchTurnIsComplete({
        status: 'completed',
        agentStatus: 'completed',
        observedWorking: false,
        restoredRun: false,
        messageCountBeforeSubmit: 4,
        currentMessageCount: 5,
      })
    ).toBe(false);
    expect(
      cadWorkbenchTurnIsComplete({
        status: 'completed',
        agentStatus: 'completed',
        observedWorking: false,
        restoredRun: false,
        messageCountBeforeSubmit: 4,
        currentMessageCount: 6,
      })
    ).toBe(true);
  });

  it('backs up the focused canonical files, assigns the visible chat, and supplies revision context', async () => {
    const preserve = vi.fn(async () => ({
      modelPath: 'models/bracket.step',
      backupPath: '.hardcore/last-good/bracket.step',
      sourcePath: 'models/bracket.py',
      sourceBackupPath: '.hardcore/last-good/bracket.py',
      recordedAt: '2026-08-29T10:00:00.000Z',
      validationStatus: 'unknown' as const,
    }));
    const identity = {
      contextKey: 'cad-model:models/bracket',
      modelPath: 'models/bracket.step',
      sourcePath: 'models/bracket.py',
    };

    const prepared = await prepareCadWorkbenchRun({
      catalog: emptyCatalog(),
      identity,
      workspacePath: '/workspace',
      conversationId: 'visible-chat',
      prompt: 'Make the bracket thicker',
      modelFiles: ['models/bracket.step', 'models/bracket.py'],
      runId: 'run-1',
      startedAt: '2026-08-29T10:00:00.000Z',
      preserve,
    });

    expect(prepared.success).toBe(true);
    if (!prepared.success) return;
    expect(preserve).toHaveBeenCalledWith(
      expect.objectContaining({
        modelPath: 'models/bracket.step',
        sourcePath: 'models/bracket.py',
        runId: 'run-1',
      })
    );
    expect(prepared.catalog.models[identity.contextKey]?.run).toMatchObject({
      id: 'run-1',
      conversationId: 'visible-chat',
      status: 'generating',
    });
    expect(prepared.hiddenContext).toContain('models/bracket.step');
    expect(prepared.hiddenContext).toContain('models/bracket.py');
    expect(prepared.hiddenContext).toContain('artifact revision');
  });

  it('validates only the canonical STEP and restores both files after a failed check', async () => {
    const validate = vi.fn(async () => ({ success: false as const, error: 'invalid solid' }));
    const restore = vi.fn(async () => {});
    const snapshot = {
      modelPath: 'models/bracket.step',
      backupPath: '.hardcore/last-good/bracket.step',
      sourcePath: 'models/bracket.py',
      sourceBackupPath: '.hardcore/last-good/bracket.py',
      recordedAt: '2026-08-29T10:00:00.000Z',
      validationStatus: 'unknown' as const,
    };

    const completed = await validateCadWorkbenchArtifact({
      workspacePath: '/workspace',
      modelPath: 'models/bracket.step',
      snapshot,
      restoreOnFailure: true,
      validate,
      restore,
    });

    expect(validate).toHaveBeenCalledWith({
      workspacePath: '/workspace',
      filePath: '/workspace/models/bracket.step',
    });
    expect(restore).toHaveBeenCalledWith({ workspacePath: '/workspace', snapshot });
    expect(completed).toMatchObject({ restored: true, result: { success: false } });
  });

  it('rebuilds instead of accepting an old STEP when the linked source changed', async () => {
    const snapshot = {
      modelPath: 'models/bracket.step',
      sourcePath: 'models/bracket.py',
      recordedAt: '2026-08-29T10:00:00.000Z',
      validationStatus: 'passed' as const,
      modelHash: 'old-step',
      sourceHash: 'old-source',
    };
    const validate = vi.fn(async () => ({
      success: true as const,
      artifact: {
        revisionId: 'sha256:old-step',
        modelPath: 'models/bracket.step',
        modelHash: 'old-step',
        sourcePath: 'models/bracket.py',
        sourceHash: 'new-source',
      },
      facts: {},
      validation: {},
    }));
    const rebuild = vi.fn(async () => ({
      success: true as const,
      artifact: {
        revisionId: 'sha256:new-step',
        modelPath: 'models/bracket.step',
        modelHash: 'new-step',
        sourcePath: 'models/bracket.py',
        sourceHash: 'new-source',
      },
      facts: {},
      validation: {},
    }));

    const completed = await validateCadWorkbenchArtifact({
      workspacePath: '/workspace',
      modelPath: 'models/bracket.step',
      sourcePath: 'models/bracket.py',
      snapshot,
      restoreOnFailure: true,
      validate,
      rebuild,
      restore: vi.fn(async () => {}),
    });

    expect(validate).toHaveBeenCalledWith({
      workspacePath: '/workspace',
      filePath: '/workspace/models/bracket.step',
      sourcePath: '/workspace/models/bracket.py',
    });
    expect(rebuild).toHaveBeenCalledWith({
      workspacePath: '/workspace',
      filePath: '/workspace/models/bracket.py',
    });
    expect(completed.result).toMatchObject({
      success: true,
      artifact: { modelHash: 'new-step', sourceHash: 'new-source' },
    });
  });

  it('rejects and restores a rebuild that leaves the canonical STEP unchanged', async () => {
    const snapshot = {
      modelPath: 'models/bracket.step',
      backupPath: '.hardcore/last-good/bracket.step',
      sourcePath: 'models/bracket.py',
      sourceBackupPath: '.hardcore/last-good/bracket.py',
      recordedAt: '2026-08-29T10:00:00.000Z',
      validationStatus: 'passed' as const,
      modelHash: 'old-step',
      sourceHash: 'old-source',
    };
    const artifact = {
      revisionId: 'sha256:old-step',
      modelPath: 'models/bracket.step',
      modelHash: 'old-step',
      sourcePath: 'models/bracket.py',
      sourceHash: 'new-source',
    };
    const rebuild = vi.fn(async () => ({
      success: true as const,
      artifact,
      facts: {},
      validation: {},
    }));
    const restore = vi.fn(async () => {});

    const completed = await validateCadWorkbenchArtifact({
      workspacePath: '/workspace',
      modelPath: 'models/bracket.step',
      sourcePath: 'models/bracket.py',
      snapshot,
      restoreOnFailure: true,
      validate: vi.fn(async () => ({
        success: true as const,
        artifact,
        facts: {},
        validation: {},
      })),
      rebuild,
      restore,
    });

    expect(rebuild).toHaveBeenCalledOnce();
    expect(completed.result).toEqual({
      success: false,
      error: 'The model source changed, but rebuilding did not update the canonical STEP.',
    });
    expect(restore).toHaveBeenCalledWith({ workspacePath: '/workspace', snapshot });
    expect(completed.restored).toBe(true);
  });

  it('restores a prepared run and releases its generating lease when dispatch fails', async () => {
    let catalog: CadModelCatalog = {
      version: '3',
      activeModelKey: 'cad-model:models/bracket',
      models: {
        'cad-model:models/bracket': {
          contextKey: 'cad-model:models/bracket',
          modelPath: 'models/bracket.step',
          sourcePath: 'models/bracket.py',
          artifacts: [
            { path: 'models/bracket.step', role: 'model' },
            { path: 'models/bracket.py', role: 'source' },
          ],
          conversations: {},
          run: { id: 'run-1', origin: 'agent', status: 'generating' },
          lastGood: {
            modelPath: 'models/bracket.step',
            backupPath: '.hardcore/last-good/bracket.step',
            sourcePath: 'models/bracket.py',
            sourceBackupPath: '.hardcore/last-good/bracket.py',
            recordedAt: '2026-08-29T10:00:00.000Z',
            validationStatus: 'unknown',
          },
          updatedAt: '2026-08-29T10:00:00.000Z',
        },
      },
    };
    const restore = vi.fn(async () => {});

    const result = await abortPreparedCadWorkbenchRun({
      contextKey: 'cad-model:models/bracket',
      runId: 'run-1',
      workspacePath: '/workspace',
      getCatalog: () => catalog,
      updateCatalog: (update) => {
        catalog = update(catalog);
      },
      restore,
    });

    expect(restore).toHaveBeenCalledOnce();
    expect(result).toMatchObject({ aborted: true, restored: true });
    expect(catalog.models['cad-model:models/bracket']?.run.status).toBe('interrupted');
  });

  it('releases the generating lease even when dispatch rollback fails', async () => {
    let catalog: CadModelCatalog = {
      version: '3',
      models: {
        'cad-model:models/bracket': {
          contextKey: 'cad-model:models/bracket',
          modelPath: 'models/bracket.step',
          artifacts: [{ path: 'models/bracket.step', role: 'model' }],
          conversations: {},
          run: { id: 'run-1', origin: 'agent', status: 'generating' },
          lastGood: {
            modelPath: 'models/bracket.step',
            backupPath: '.hardcore/last-good/bracket.step',
            recordedAt: '2026-08-29T10:00:00.000Z',
            validationStatus: 'unknown',
          },
          updatedAt: '2026-08-29T10:00:00.000Z',
        },
      },
    };

    const result = await abortPreparedCadWorkbenchRun({
      contextKey: 'cad-model:models/bracket',
      runId: 'run-1',
      workspacePath: '/workspace',
      getCatalog: () => catalog,
      updateCatalog: (update) => {
        catalog = update(catalog);
      },
      restore: vi.fn(async () => {
        throw new Error('Recovery file unreadable');
      }),
    });

    expect(result).toMatchObject({
      aborted: true,
      restored: false,
      restoreError: 'Recovery file unreadable',
    });
    expect(catalog.models['cad-model:models/bracket']?.run.status).toBe('interrupted');
  });
});

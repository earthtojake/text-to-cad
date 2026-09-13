import { describe, expect, it, vi } from 'vitest';
import {
  acquireCadSourceRunOwnership,
  clearCadSourceRunOwnership,
  clearCadTaskRunOwnership,
  getFocusedCadArtifact,
  getCadTaskRunOwnership,
  isCadSourceRunLocallyOwned,
  recordFocusedCadArtifact,
  recordCadTaskRunOwnership,
  refreshCadTaskRunArtifact,
  registerCadTaskRunRefreshHandler,
  resetCadTaskRunRuntimeForTests,
} from './cad-task-run-runtime';

describe('CAD task run runtime', () => {
  const model = { projectId: 'project', taskId: 'task', contextKey: 'cad-model:bracket' };

  it('keeps origin-run ownership after the focused artifact unregisters', () => {
    resetCadTaskRunRuntimeForTests();
    const refresh = vi.fn();
    const unregisterFocus = registerCadTaskRunRefreshHandler(model, refresh);
    recordCadTaskRunOwnership({
      ...model,
      runId: 'run-1',
      conversationId: 'chat-1',
      messageCountBeforeSubmit: 4,
    });

    unregisterFocus();

    expect(getCadTaskRunOwnership(model)).toMatchObject({ runId: 'run-1' });
    refreshCadTaskRunArtifact(model);
    expect(refresh).not.toHaveBeenCalled();
    clearCadTaskRunOwnership(model, 'run-1');
    expect(getCadTaskRunOwnership(model)).toBeUndefined();
  });

  it('does not let an obsolete watcher clear a newer run', () => {
    resetCadTaskRunRuntimeForTests();
    recordCadTaskRunOwnership({
      ...model,
      runId: 'run-2',
      conversationId: 'chat-2',
      messageCountBeforeSubmit: 8,
    });

    clearCadTaskRunOwnership(model, 'run-1');

    expect(getCadTaskRunOwnership(model)?.runId).toBe('run-2');
  });

  it('distinguishes a live direct rebuild from a source run recovered after restart', () => {
    resetCadTaskRunRuntimeForTests();

    expect(acquireCadSourceRunOwnership(model, 'source-run-1')).toBe(true);
    expect(isCadSourceRunLocallyOwned(model, 'source-run-1')).toBe(true);
    expect(acquireCadSourceRunOwnership(model, 'source-run-2')).toBe(false);

    clearCadSourceRunOwnership(model, 'source-run-2');
    expect(isCadSourceRunLocallyOwned(model, 'source-run-1')).toBe(true);
    clearCadSourceRunOwnership(model, 'source-run-1');
    expect(isCadSourceRunLocallyOwned(model, 'source-run-1')).toBe(false);
  });

  it('retains the last explicitly focused artifact when focus returns to chat', () => {
    resetCadTaskRunRuntimeForTests();
    recordFocusedCadArtifact({ ...model, contextKey: 'cad-model:plate' });
    recordFocusedCadArtifact({ ...model, contextKey: 'cad-model:bracket' });

    expect(getFocusedCadArtifact(model)).toBe('cad-model:bracket');
  });
});

import { describe, expect, it, vi } from 'vitest';
import {
  combineWorkbenchHiddenContext,
  prepareWorkbenchChatSubmission,
  registerWorkbenchChatSubmissionHandler,
  resetWorkbenchChatSubmissionBridgeForTests,
} from './workbench-chat-submit-bridge';

describe('workbench chat submission bridge', () => {
  const target = { projectId: 'project', taskId: 'task' };

  it('uses the active artifact handler without changing the shared composer API', async () => {
    resetWorkbenchChatSubmissionBridgeForTests();
    const unregister = registerWorkbenchChatSubmissionHandler(target, async (submission) => ({
      success: true,
      hiddenContext: `Focused file: ${submission.text}`,
    }));

    await expect(
      prepareWorkbenchChatSubmission(target, {
        conversationId: 'chat',
        text: 'bracket.step',
        messageCountBeforeSubmit: 4,
        agentIsWorking: false,
      })
    ).resolves.toEqual({ success: true, hiddenContext: 'Focused file: bracket.step' });

    unregister();
    await expect(
      prepareWorkbenchChatSubmission(target, {
        conversationId: 'chat',
        text: 'bracket.step',
        messageCountBeforeSubmit: 4,
        agentIsWorking: false,
      })
    ).resolves.toEqual({
      success: false,
      error: 'The engineering artifact lifecycle is not ready. Wait a moment and try again.',
    });
  });

  it('fails closed before a task-owned artifact lifecycle handler is ready', async () => {
    resetWorkbenchChatSubmissionBridgeForTests();

    await expect(
      prepareWorkbenchChatSubmission(target, {
        conversationId: 'chat',
        text: 'Make the bracket thinner',
        messageCountBeforeSubmit: 0,
        agentIsWorking: false,
      })
    ).resolves.toEqual({
      success: false,
      error: 'The engineering artifact lifecycle is not ready. Wait a moment and try again.',
    });
  });

  it('does not let an obsolete artifact unregister the newer active artifact', async () => {
    resetWorkbenchChatSubmissionBridgeForTests();
    const unregisterOld = registerWorkbenchChatSubmissionHandler(target, async () => ({
      success: true,
      hiddenContext: 'old',
    }));
    registerWorkbenchChatSubmissionHandler(target, async () => ({
      success: true,
      hiddenContext: 'new',
    }));

    unregisterOld();
    await expect(
      prepareWorkbenchChatSubmission(target, {
        conversationId: 'chat',
        text: 'edit',
        messageCountBeforeSubmit: 0,
        agentIsWorking: false,
      })
    ).resolves.toMatchObject({ hiddenContext: 'new' });
  });

  it('combines issue and artifact context without exposing either in the visible prompt', () => {
    expect(combineWorkbenchHiddenContext('Issue context', undefined, 'CAD context')).toBe(
      'Issue context\n\nCAD context'
    );
  });

  it('carries an artifact rollback callback without coupling the composer to CAD', async () => {
    resetWorkbenchChatSubmissionBridgeForTests();
    const rollback = vi.fn(async () => ({ success: true as const }));
    registerWorkbenchChatSubmissionHandler(target, async () => ({
      success: true,
      onDispatchFailure: rollback,
    }));

    const preparation = await prepareWorkbenchChatSubmission(target, {
      conversationId: 'chat',
      text: 'edit',
      messageCountBeforeSubmit: 0,
      agentIsWorking: false,
    });
    expect(preparation.success).toBe(true);
    if (!preparation.success) return;

    await expect(preparation.onDispatchFailure?.('Provider unavailable')).resolves.toEqual({
      success: true,
    });
    expect(rollback).toHaveBeenCalledWith('Provider unavailable');
  });
});

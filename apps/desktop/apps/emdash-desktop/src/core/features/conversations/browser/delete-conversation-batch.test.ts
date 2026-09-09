import { describe, expect, it, vi } from 'vitest';
import { deleteConversationBatch } from './delete-conversation-batch';

describe('deleteConversationBatch', () => {
  it('deletes each unique conversation', async () => {
    const deleteConversation = vi.fn(async () => undefined);

    const result = await deleteConversationBatch(
      ['conversation-1', 'conversation-2', 'conversation-1'],
      deleteConversation
    );

    expect(deleteConversation.mock.calls).toEqual([['conversation-1'], ['conversation-2']]);
    expect(result).toEqual({
      succeededIds: ['conversation-1', 'conversation-2'],
      failures: [],
    });
  });

  it('reports individual failures without discarding successful deletions', async () => {
    const error = new Error('Could not delete conversation-2');
    const deleteConversation = vi.fn(async (conversationId: string) => {
      if (conversationId === 'conversation-2') throw error;
    });

    const result = await deleteConversationBatch(
      ['conversation-1', 'conversation-2', 'conversation-3'],
      deleteConversation
    );

    expect(result).toEqual({
      succeededIds: ['conversation-1', 'conversation-3'],
      failures: [{ conversationId: 'conversation-2', error }],
    });
  });
});

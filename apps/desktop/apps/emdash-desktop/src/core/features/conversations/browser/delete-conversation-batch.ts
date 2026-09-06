export interface ConversationDeleteFailure {
  conversationId: string;
  error: unknown;
}

export interface ConversationBatchDeleteResult {
  succeededIds: string[];
  failures: ConversationDeleteFailure[];
}

export async function deleteConversationBatch(
  conversationIds: Iterable<string>,
  deleteConversation: (conversationId: string) => Promise<void>
): Promise<ConversationBatchDeleteResult> {
  const uniqueIds = [...new Set(conversationIds)];
  const results = await Promise.allSettled(
    uniqueIds.map(async (conversationId) => {
      await deleteConversation(conversationId);
      return conversationId;
    })
  );

  const succeededIds: string[] = [];
  const failures: ConversationDeleteFailure[] = [];
  results.forEach((result, index) => {
    const conversationId = uniqueIds[index]!;
    if (result.status === 'fulfilled') {
      succeededIds.push(conversationId);
    } else {
      failures.push({ conversationId, error: result.reason });
    }
  });

  return { succeededIds, failures };
}

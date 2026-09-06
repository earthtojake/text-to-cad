import { getSearchClient, type SearchClient } from '@core/features/search/api/client';
import {
  matchPaletteText,
  type PaletteContext,
  type PaletteProviderMatch,
  type PaletteProviderQuery,
} from '@core/primitives/palette/api';
import type { SearchItem } from '@core/primitives/search/api';

const RECENT_CONVERSATION_LIMIT = 5;
const CONVERSATION_CANDIDATE_LIMIT = 50;

type ConversationSearchClient = Pick<SearchClient, 'searchPaletteEntities'>;
type GetConversationSearchClient = () => Promise<ConversationSearchClient>;

interface ConversationSearchItem extends SearchItem {
  readonly kind: 'conversation';
  readonly projectId: string;
  readonly taskId: string;
}

export interface ConversationPaletteMatch extends PaletteProviderMatch {
  readonly item: ConversationSearchItem;
}

export interface ConversationPaletteSource {
  readonly idle: (context: PaletteContext) => Promise<ConversationPaletteMatch[]>;
  readonly search: (input: PaletteProviderQuery) => Promise<ConversationPaletteMatch[]>;
}

function asContextConversation(
  item: SearchItem,
  context: PaletteContext
): ConversationSearchItem | undefined {
  if (
    item.kind !== 'conversation' ||
    !item.projectId ||
    !item.taskId ||
    item.taskId !== context.taskId ||
    (context.projectId !== undefined && item.projectId !== context.projectId)
  ) {
    return undefined;
  }
  return item as ConversationSearchItem;
}

function toIdleMatch(item: ConversationSearchItem): ConversationPaletteMatch {
  return {
    id: item.id,
    item,
    title: item.title,
    subtitle: item.subtitle,
    section: 'Recent Conversations',
    relevance: {
      band: 'fuzzy',
      score: 0,
      contextAffinity: 1,
    },
  };
}

function toTypedMatch(
  item: ConversationSearchItem,
  query: string
): ConversationPaletteMatch | undefined {
  const relevance = matchPaletteText(query, { primary: [item.title] });
  if (!relevance) return undefined;
  return {
    id: item.id,
    item,
    title: item.title,
    subtitle: item.subtitle,
    relevance: {
      ...relevance,
      contextAffinity: 1,
    },
  };
}

export function createConversationPaletteSource(
  getClient: GetConversationSearchClient = getSearchClient
): ConversationPaletteSource {
  return {
    async idle(context) {
      if (!context.taskId) return [];
      const client = await getClient();
      const candidates = await client.searchPaletteEntities({
        kind: 'conversation',
        query: '',
        context,
        limit: RECENT_CONVERSATION_LIMIT,
      });
      return candidates
        .flatMap((candidate) => {
          const item = asContextConversation(candidate, context);
          return item ? [toIdleMatch(item)] : [];
        })
        .slice(0, RECENT_CONVERSATION_LIMIT);
    },

    async search({ query, context }) {
      if (!context.taskId) return [];
      const client = await getClient();
      const candidates = await client.searchPaletteEntities({
        kind: 'conversation',
        query,
        context,
        limit: CONVERSATION_CANDIDATE_LIMIT,
      });
      return candidates.flatMap((candidate) => {
        const item = asContextConversation(candidate, context);
        if (!item) return [];
        const match = toTypedMatch(item, query);
        return match ? [match] : [];
      });
    },
  };
}

export const conversationPaletteSource = createConversationPaletteSource();

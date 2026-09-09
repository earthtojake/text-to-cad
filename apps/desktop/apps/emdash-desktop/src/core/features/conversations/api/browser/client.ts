import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { conversationsContract, conversationsDomain } from '../contract';

export type ConversationsClient = ContractClient<typeof conversationsContract>;

export function getConversationsClient(): Promise<ConversationsClient> {
  return domainClient<ConversationsClient>(conversationsDomain, conversationsContract);
}

import { defineContract, fallible } from '@emdash/wire/rpc';
import {
  conversationIndexRecordSchema,
  createConversationIndexRecordErrorSchema,
  createConversationIndexRecordInputSchema,
} from './schemas';

/**
 * The record-creation subset of the conversations index contract (spec §4.1): the surface
 * host-side record creators (the automations runtime) depend on. Structurally a subset of
 * `conversationsContract`, so the full conversations client satisfies it — the
 * session-start-contract pattern.
 */
export const conversationIndexContract = defineContract({
  create: fallible({
    input: createConversationIndexRecordInputSchema,
    data: conversationIndexRecordSchema,
    error: createConversationIndexRecordErrorSchema,
  }),
});

export type ConversationIndexContract = typeof conversationIndexContract;

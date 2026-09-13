import { z } from 'zod';
import { defineVersionedSchema } from '#primitives/versioned-schema/api';
import {
  conversationConfigSchema,
  conversationIdRegimeSchema,
  type ConversationConfig,
  type ConversationIdRegime,
} from '../../api/schemas';

const storedConversationConfigV1Schema = z.object({
  version: z.literal('1'),
  value: conversationConfigSchema,
});

const storedConversationConfig = defineVersionedSchema()
  .initial('1', storedConversationConfigV1Schema)
  .build();

/** Provider session linkage sub-record (spec §3.1): last-observed pointer, never identity. */
export type ProviderLink = {
  providerSessionId: string | null;
  idRegime: ConversationIdRegime;
  observedAt: number | null;
};

const storedProviderLinkV1Schema = z.object({
  version: z.literal('1'),
  providerSessionId: z.string().nullable(),
  idRegime: conversationIdRegimeSchema,
  observedAt: z.number().nullable(),
});

const storedProviderLink = defineVersionedSchema().initial('1', storedProviderLinkV1Schema).build();

export function serializeConfigPayload(config: ConversationConfig): string {
  return storedConversationConfig.serialize({ version: '1', value: config });
}

export function parseConfigPayload(payload: string): ConversationConfig {
  const result = storedConversationConfig.safeParse(parsePayload(payload, 'config'));
  if (result.status !== 'ok') {
    throw new Error(`Unable to parse stored conversation config: ${describeFailure(result)}`);
  }
  return result.data.value;
}

export function serializeProviderLinkPayload(link: ProviderLink): string {
  return storedProviderLink.serialize({ version: '1', ...link });
}

export function parseProviderLinkPayload(payload: string): ProviderLink {
  const result = storedProviderLink.safeParse(parsePayload(payload, 'provider link'));
  if (result.status !== 'ok') {
    throw new Error(`Unable to parse stored provider link: ${describeFailure(result)}`);
  }
  const { version: _version, ...link } = result.data;
  return link;
}

function parsePayload(payload: string, label: string): unknown {
  try {
    return JSON.parse(payload);
  } catch (error) {
    throw new Error(`Stored conversation ${label} contains invalid JSON`, { cause: error });
  }
}

function describeFailure(
  result:
    | { status: 'needs-context'; version: string }
    | { status: 'future-version'; version: string }
    | { status: 'invalid'; reason: string }
): string {
  return result.status === 'invalid' ? result.reason : `${result.status} '${result.version}'`;
}

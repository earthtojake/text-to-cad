import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import z from 'zod';

// ---------------------------------------------------------------------------
// v1 schema — initial version
// ---------------------------------------------------------------------------

/**
 * Display and identity metadata for a provider account. Every field is
 * optional: providers without a real account identity (single-token
 * integrations) store little or nothing here, while providers like GitHub
 * populate the full identity block. New fields must be added as optional so
 * existing rows stay valid without a schema version bump.
 */
const v1Schema = z.object({
  version: z.literal('1'),
  /** Human-readable account label, e.g. "Mona Lisa" or a Jira site name. */
  displayName: z.string().optional(),
  /** Provider login/username, e.g. "octocat". */
  login: z.string().optional(),
  avatarUrl: z.string().optional(),
  /** Provider host the account belongs to, e.g. "github.com". */
  host: z.string().optional(),
  /** The provider's own id for the account, e.g. a numeric GitHub user id. */
  providerAccountId: z.string().optional(),
  /** How the credential was obtained, e.g. 'form' | 'oauth' | 'device_flow' | 'cli'. */
  credentialSource: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Versioned schema
// ---------------------------------------------------------------------------

/**
 * Versioned schema for provider account metadata stored in
 * `provider_accounts.meta`. Stable identity/constraint facts (providerId,
 * accountId, credentialRef, isDefault) live in dedicated columns; everything
 * display- or identity-shaped lives here so it can evolve additively.
 */
export const providerAccountMeta = defineVersionedSchema().initial('1', v1Schema).build();

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/** The Zod schema for the latest provider account meta shape. */
export const providerAccountMetaSchema = providerAccountMeta.schema;

/** The TypeScript type for provider account metadata. */
export type ProviderAccountMeta = typeof providerAccountMeta.Type;

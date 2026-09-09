import type { HostDependencySelection } from '@emdash/core/primitives/host-dependencies/api';
import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import z from 'zod';
import type { SshConfig } from './ssh';

// ---------------------------------------------------------------------------
// v0 schema — unversioned legacy format
// ---------------------------------------------------------------------------

const v0Schema = z.object({
  sshConfigAlias: z.string().optional(),
  forwardAgent: z.boolean().optional(),
  proxyJump: z.string().optional(),
});

// ---------------------------------------------------------------------------
// v1 schema — adds per-agent host-scoped dependency selections (legacy format)
// ---------------------------------------------------------------------------

const legacyHostDependencySelectionSchema = z.object({
  usedId: z.string().optional(),
  path: z.string().optional(),
  cli: z.string().optional(),
});

const v1Schema = v0Schema.extend({
  /**
   * Per-agent installation selections (legacy {usedId?,path?,cli?} format).
   * Keys are DependencyId; values are the user's choice.
   */
  dependencySelections: z.record(z.string(), legacyHostDependencySelectionSchema).optional(),
});

// ---------------------------------------------------------------------------
// v2 schema — InstallOverride | null per agent (override-only; null = auto)
// ---------------------------------------------------------------------------

const installOverrideV2Schema = z.nullable(
  z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('method'), method: z.string() }),
    z.object({ kind: z.literal('path'), path: z.string() }),
    z.object({ kind: z.literal('cli'), command: z.string() }),
  ])
);

const v2Schema = v0Schema.extend({
  /**
   * Per-agent installation override selections for this SSH host.
   * Keys are DependencyId; null value means auto (no override).
   *
   * v2 format: InstallOverride | null (discriminated union or null).
   */
  dependencySelections: z.record(z.string(), installOverrideV2Schema).optional(),
});

// ---------------------------------------------------------------------------
// v3 schema — adds 'pinned' kind to installOverrideSchema (pass-through migration)
// ---------------------------------------------------------------------------

const installOverrideV3Schema = z.nullable(
  z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('pinned'), realpath: z.string() }),
    z.object({ kind: z.literal('method'), method: z.string() }),
    z.object({ kind: z.literal('path'), path: z.string() }),
    z.object({ kind: z.literal('cli'), command: z.string() }),
  ])
);

const v3Schema = v0Schema.extend({
  /**
   * Per-agent installation override selections for this SSH host.
   * v3 adds { kind: 'pinned', realpath } to the override union.
   * Existing method/path/cli overrides remain valid unchanged.
   */
  dependencySelections: z.record(z.string(), installOverrideV3Schema).optional(),
});

// ---------------------------------------------------------------------------
// v4 schema — adds syncLocalSettings (opt-in per-host "Sync local settings")
// ---------------------------------------------------------------------------

const v4Schema = v3Schema.extend({
  /**
   * Declared (unlike earlier versions) so dev-mode validation does not strip
   * the version marker from parsed data before it is written back.
   */
  version: z.literal('4').optional(),
  /**
   * Opt-in "Sync local settings" toggle for this host: while true, this
   * desktop mirrors its local settings in this class (currently
   * files.watcherExclude) into the host's host-settings file on attach and on
   * local change. Absent means false (off). Desktop-side state — it describes
   * this desktop's relationship to the host.
   */
  syncLocalSettings: z.boolean().optional(),
});

// ---------------------------------------------------------------------------
// Versioned schema
// ---------------------------------------------------------------------------

/**
 * Versioned schema for SSH connection metadata stored in `sshConnections.metadata`.
 *
 * The stored object is intentionally small: only fields that cannot be captured
 * in dedicated DB columns live here.
 *
 * v0 (unversioned): sshConfigAlias, forwardAgent, proxyJump
 * v1: adds dependencySelections ({usedId?,path?,cli?} legacy format)
 * v2: migrates dependencySelections to InstallOverride | null (override-only)
 * v3: adds { kind: 'pinned', realpath } to installOverrideSchema (pass-through)
 * v4: adds syncLocalSettings (absent = false; pass-through)
 */
export const sshConnectionMetadata = defineVersionedSchema()
  .unversioned(v0Schema)
  .version('1', v1Schema, (prev) => ({ ...prev, version: '1' }))
  .version('2', v2Schema, (prev) => {
    const legacySelections = prev.dependencySelections ?? {};
    const entries = Object.entries(legacySelections);
    if (entries.length === 0) {
      const { dependencySelections: _omit, ...rest } = prev;
      return { ...rest, version: '2' };
    }
    const migratedSelections: Record<string, z.infer<typeof installOverrideV2Schema>> = {};
    for (const [depId, raw] of entries) {
      // Legacy selections never contain 'pinned'; safe to cast to v2 type.
      migratedSelections[depId] = normalizeSelection(raw) as z.infer<
        typeof installOverrideV2Schema
      >;
    }
    return {
      ...prev,
      version: '2',
      dependencySelections: migratedSelections,
    };
  })
  .version('3', v3Schema, (prev) => ({
    // Pass-through: existing method/path/cli overrides are valid in v3.
    // New 'pinned' overrides can only be created going forward.
    ...prev,
    version: '3',
  }))
  .version('4', v4Schema, (prev) => ({
    // Pass-through: syncLocalSettings stays unset (false) for existing hosts.
    ...prev,
    version: '4' as const,
  }))
  .build();

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/** The TypeScript type for SSH connection metadata. */
export type SshConnectionMetadata = typeof sshConnectionMetadata.Type;

function normalizeSelection(raw: unknown): z.infer<typeof installOverrideV2Schema> {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== 'object') return null;
  const value = raw as {
    kind?: unknown;
    path?: unknown;
    command?: unknown;
    usedId?: unknown;
    cli?: unknown;
  };
  if (value.kind === 'path' && typeof value.path === 'string')
    return { kind: 'path', path: value.path };
  if (value.kind === 'cli' && typeof value.command === 'string') {
    return { kind: 'cli', command: value.command };
  }
  if (typeof value.path === 'string') return { kind: 'path', path: value.path };
  if (typeof value.cli === 'string') return { kind: 'cli', command: value.cli };
  return null;
}

// ---------------------------------------------------------------------------
// Metadata merge and row-mapping helpers
// ---------------------------------------------------------------------------

type SshConnectionMetadataUpdate = {
  sshConfigAlias?: string;
  forwardAgent?: boolean;
  proxyJump?: string;
};

const SSH_ALIAS_PATTERN = /^[\w.@%+:/[\]-]+$/;

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function optionalSshConfigAlias(value: unknown): string | undefined {
  const alias = optionalString(value);
  if (!alias) return undefined;
  if (alias.startsWith('-') || !SSH_ALIAS_PATTERN.test(alias)) {
    throw new Error(`Invalid SSH config alias: ${alias}`);
  }
  return alias;
}

export function mergeSshConnectionMetadata(
  existing: SshConnectionMetadata,
  update: SshConnectionMetadataUpdate
): SshConnectionMetadata {
  const has = (key: keyof SshConnectionMetadataUpdate) =>
    Object.prototype.hasOwnProperty.call(update, key);

  return {
    ...existing,
    sshConfigAlias: has('sshConfigAlias')
      ? optionalSshConfigAlias(update.sshConfigAlias)
      : existing.sshConfigAlias,
    forwardAgent: has('forwardAgent') ? update.forwardAgent : existing.forwardAgent,
    proxyJump: has('proxyJump') ? optionalString(update.proxyJump) : existing.proxyJump,
  };
}

/** Merge a single dependency selection into the existing SSH connection metadata. */
export function mergeDependencySelection(
  existing: SshConnectionMetadata,
  depId: string,
  selection: HostDependencySelection
): SshConnectionMetadata {
  return {
    ...existing,
    dependencySelections: {
      ...existing.dependencySelections,
      [depId]: selection,
    },
  };
}

/**
 * The `sshConnections` row fields needed to reconstruct an SshConfig. Kept
 * structural so this primitive does not import the app-db schema (which itself
 * consumes the metadata schema above).
 */
export type SshConnectionConfigRow = {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  authType: string;
  privateKeyPath: string | null;
  useAgent: number;
  metadata: SshConnectionMetadata | null;
};

export function sshConfigFromRow(row: SshConnectionConfigRow): SshConfig {
  const metadata = row.metadata ?? {};
  return {
    id: row.id,
    name: row.name,
    host: row.host,
    port: row.port,
    username: row.username,
    authType: row.authType as 'password' | 'key' | 'agent',
    privateKeyPath: row.privateKeyPath ?? undefined,
    useAgent: row.useAgent === 1,
    sshConfigAlias: metadata.sshConfigAlias,
    forwardAgent: metadata.forwardAgent,
    proxyJump: metadata.proxyJump,
    syncLocalSettings: metadata.syncLocalSettings,
  };
}

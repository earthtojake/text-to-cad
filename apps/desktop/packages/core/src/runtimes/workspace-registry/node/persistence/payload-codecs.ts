import { z } from 'zod';
import { defineVersionedSchema } from '#primitives/versioned-schema/api';
import {
  workspaceCreateOutcomeSchema,
  workspaceCreationSchema,
  workspaceGitObservationsSchema,
  workspaceLifecycleSchema,
  personalProjectConfigSchema,
  workspaceRemovalAttemptSchema,
  type WorkspaceCreateOutcome,
  type WorkspaceCreation,
  type WorkspaceGitObservations,
  type WorkspaceLifecycle,
  type WorkspaceLifecycleStep,
  type WorkspaceRemovalAttempt,
  type PersonalProjectConfig,
} from '../../api/schemas';

const storedCreation = defineVersionedSchema()
  .initial('1', z.object({ version: z.literal('1'), value: workspaceCreationSchema }))
  .build();

const storedCreateOutcome = defineVersionedSchema()
  .initial('1', z.object({ version: z.literal('1'), value: workspaceCreateOutcomeSchema }))
  .build();

/**
 * v2 added headOid, upstream identity, and the PR breadcrumb with NO v1 upcast:
 * observations are re-derivable facts, so a stored v1 payload reads as null
 * (not-yet-observed — the unknown version short-circuits before any schema
 * validation) and the next scan writes v2.
 */
const storedGitObservations = defineVersionedSchema()
  .initial('2', z.object({ version: z.literal('2'), value: workspaceGitObservationsSchema }))
  .build();

const storedRemovalAttempt = defineVersionedSchema()
  .initial('1', z.object({ version: z.literal('1'), value: workspaceRemovalAttemptSchema }))
  .build();

const storedPersonalProjectConfig = defineVersionedSchema()
  .initial('1', z.object({ version: z.literal('1'), value: personalProjectConfigSchema }))
  .build();

// The pre-lifecycle shape of the `background` column (v1): fixed per-step slots with a
// single transition stamp. Kept only for the v1 → v2 upgrade of existing rows.
const legacyBackgroundStepSchema = z.object({
  status: z.enum(['pending', 'running', 'succeeded', 'failed', 'skipped']),
  at: z.number(),
  message: z.string().optional(),
});
type LegacyBackgroundStep = z.infer<typeof legacyBackgroundStepSchema>;

const legacyBackgroundSchema = z.object({
  steps: z.object({
    cloneArtifacts: legacyBackgroundStepSchema.nullable(),
    pushBranch: legacyBackgroundStepSchema.nullable(),
    fetchRefs: legacyBackgroundStepSchema.nullable(),
  }),
  preservePatterns: z.array(z.string()),
});
type LegacyBackground = z.infer<typeof legacyBackgroundSchema>;

/**
 * The `background` column now stores the unified lifecycle section; v1 payloads (the
 * old background-steps shape) upgrade in place, best-effort — the legacy single `at`
 * stamp becomes startedAt/finishedAt as its status implies.
 */
const storedLifecycle = defineVersionedSchema()
  .initial('1', z.object({ version: z.literal('1'), value: legacyBackgroundSchema }))
  .version('2', z.object({ version: z.literal('2'), value: workspaceLifecycleSchema }), (prev) => ({
    version: '2' as const,
    value: migrateLegacyBackground(prev.value),
  }))
  .build();

function migrateLegacyBackground(legacy: LegacyBackground): WorkspaceLifecycle {
  const steps: WorkspaceLifecycleStep[] = [];
  const append = (
    id: 'copy-artifacts' | 'push-branch' | 'fetch-refs',
    step: LegacyBackgroundStep | null
  ) => {
    if (step === null) return;
    const terminal = step.status !== 'pending' && step.status !== 'running';
    steps.push({
      id,
      status: step.status,
      startedAt: step.status === 'pending' ? null : step.at,
      finishedAt: terminal ? step.at : null,
      ...(step.message !== undefined ? { message: step.message } : {}),
      params: {},
    });
  };
  append('copy-artifacts', legacy.steps.cloneArtifacts);
  append('push-branch', legacy.steps.pushBranch);
  append('fetch-refs', legacy.steps.fetchRefs);
  return { steps, preservePatterns: legacy.preservePatterns };
}

export function serializeCreationPayload(creation: WorkspaceCreation): string {
  return storedCreation.serialize({ version: '1', value: creation });
}

export function parseCreationPayload(payload: string): WorkspaceCreation {
  return parseVersioned(storedCreation, payload, 'creation');
}

export function serializeCreateOutcomePayload(outcome: WorkspaceCreateOutcome): string {
  return storedCreateOutcome.serialize({ version: '1', value: outcome });
}

export function parseCreateOutcomePayload(payload: string): WorkspaceCreateOutcome {
  return parseVersioned(storedCreateOutcome, payload, 'create outcome');
}

export function serializeGitObservationsPayload(git: WorkspaceGitObservations): string {
  return storedGitObservations.serialize({ version: '2', value: git });
}

/**
 * Unlike the other payloads, git observations are pure scan output: a payload that no
 * longer parses (an old version, corrupt JSON) degrades to null — not-yet-observed —
 * and the next scan rewrites it. Never a crash.
 */
export function parseGitObservationsPayload(payload: string): WorkspaceGitObservations | null {
  let json: unknown;
  try {
    json = JSON.parse(payload);
  } catch {
    return null;
  }
  const result = storedGitObservations.safeParse(json);
  return result.status === 'ok' ? result.data.value : null;
}

export function serializeRemovalAttemptPayload(attempt: WorkspaceRemovalAttempt): string {
  return storedRemovalAttempt.serialize({ version: '1', value: attempt });
}

export function parseRemovalAttemptPayload(payload: string): WorkspaceRemovalAttempt {
  return parseVersioned(storedRemovalAttempt, payload, 'removal attempt');
}

export function serializeLifecyclePayload(lifecycle: WorkspaceLifecycle): string {
  return storedLifecycle.serialize({ version: '2', value: lifecycle });
}

export function parseLifecyclePayload(payload: string): WorkspaceLifecycle {
  return parseVersioned(storedLifecycle, payload, 'lifecycle steps');
}

export function serializePersonalProjectConfigPayload(config: PersonalProjectConfig): string {
  return storedPersonalProjectConfig.serialize({ version: '1', value: config });
}

export function parsePersonalProjectConfigPayload(payload: string): PersonalProjectConfig {
  return parseVersioned(storedPersonalProjectConfig, payload, 'personal config');
}

type VersionedEnvelope<T> = {
  safeParse(
    input: unknown
  ):
    | { status: 'ok'; data: { version: string; value: T } }
    | { status: 'needs-context'; version: string }
    | { status: 'future-version'; version: string }
    | { status: 'invalid'; reason: string };
};

function parseVersioned<T>(schema: VersionedEnvelope<T>, payload: string, label: string): T {
  let json: unknown;
  try {
    json = JSON.parse(payload);
  } catch (error) {
    throw new Error(`Stored workspace ${label} contains invalid JSON`, { cause: error });
  }
  const result = schema.safeParse(json);
  if (result.status !== 'ok') {
    const detail = result.status === 'invalid' ? result.reason : `${result.status}`;
    throw new Error(`Unable to parse stored workspace ${label}: ${detail}`);
  }
  return result.data.value;
}

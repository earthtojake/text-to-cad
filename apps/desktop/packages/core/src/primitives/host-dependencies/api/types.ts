import { resultSchema } from '@emdash/shared';
import type { Result } from '@emdash/shared';
import { z } from 'zod';
import {
  hostDependencyDescriptorSchema,
  installCommandOptionSchema,
  installMethodSchema,
  type DependencyStatus,
  type InstallMethod,
  type Platform,
  type ProbeResult,
  type hostDependencyUpdateCommandSchema,
} from './capability';

export type DependencyCategory = 'core' | 'agent';

export type DependencyId = string;

export const dependencyCategorySchema = z.enum(['core', 'agent']);
export const dependencyIdSchema = z.string().min(1);
export const dependencyStatusSchema = z.enum(['available', 'missing', 'error']);
export const hostElevationSchema = z.enum(['root', 'passwordless-sudo', 'unavailable']);
export type HostElevation = z.output<typeof hostElevationSchema>;

export const hostDependencyDefinitionSchema = hostDependencyDescriptorSchema.extend({
  name: z.string(),
  category: dependencyCategorySchema,
  status: z.enum(['active', 'deprecated']).default('active'),
  deprecatedAt: z.number().nullable().optional(),
});
export type HostDependencyDefinition = z.output<typeof hostDependencyDefinitionSchema>;

export const hostDependencySelectionSchema = z
  .object({
    kind: z.literal('path'),
    path: z.string().min(1),
  })
  .nullable();
export type HostDependencySelection = z.output<typeof hostDependencySelectionSchema>;

export const pathCandidateSchema = z.object({
  command: z.string(),
  path: z.string(),
  realpath: z.string(),
  isPathDefault: z.boolean(),
});
export type PathCandidate = z.output<typeof pathCandidateSchema>;

export const resolvedHostDependencySchema = z.object({
  id: dependencyIdSchema,
  command: z.string(),
  path: z.string(),
  realpath: z.string(),
  source: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('auto') }),
    z.object({ kind: z.literal('path'), path: z.string() }),
  ]),
});
export type ResolvedHostDependency = z.output<typeof resolvedHostDependencySchema>;

export const hostDependencyErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('unknown-dependency'), id: dependencyIdSchema }),
  z.object({ type: z.literal('missing'), id: dependencyIdSchema }),
  z.object({ type: z.literal('stale-selection'), id: dependencyIdSchema, path: z.string() }),
  z.object({ type: z.literal('invalid-selection'), id: dependencyIdSchema, message: z.string() }),
  z.object({ type: z.literal('no-install-command'), id: dependencyIdSchema }),
  z.object({
    type: z.literal('not-detected-after-install'),
    id: dependencyIdSchema,
    output: z.string().optional(),
  }),
  z.object({ type: z.literal('no-update-command'), id: dependencyIdSchema }),
  z.object({
    type: z.literal('installer-missing'),
    id: dependencyIdSchema,
    tool: z.string().min(1),
    method: installMethodSchema,
  }),
  z.object({
    type: z.literal('permission-denied'),
    id: dependencyIdSchema,
    message: z.string(),
    output: z.string().optional(),
    exitCode: z.number().nullable().optional(),
    canRetryWithSudo: z.boolean().optional(),
    elevatedCommand: z.string().optional(),
    interactiveCommand: z.string().optional(),
    command: z.string().optional(),
  }),
  z.object({
    type: z.literal('command-failed'),
    message: z.string(),
    output: z.string(),
    exitCode: z.number().nullable().optional(),
  }),
  z.object({ type: z.literal('io'), message: z.string() }),
]);
export type HostDependencyError = z.output<typeof hostDependencyErrorSchema>;
export type PermissionDeniedError = Extract<HostDependencyError, { type: 'permission-denied' }>;

export const hostDependencyViewSchema = z.object({
  hostId: z.string(),
  definition: hostDependencyDefinitionSchema,
  installOptions: z.array(installCommandOptionSchema),
  selection: hostDependencySelectionSchema,
  candidates: z.array(pathCandidateSchema),
  resolved: resolvedHostDependencySchema.nullable(),
  status: dependencyStatusSchema,
  checkedAt: z.number(),
  error: hostDependencyErrorSchema.optional(),
});
export type HostDependencyView = z.output<typeof hostDependencyViewSchema>;

export const hostDependencySnapshotSchema = z.object({
  hostId: z.string(),
  generation: z.number().int().nonnegative(),
  hostElevation: hostElevationSchema.nullable(),
  dependencies: z.record(dependencyIdSchema, hostDependencyViewSchema),
});
export type HostDependencySnapshot = z.output<typeof hostDependencySnapshotSchema>;

export const hostDependencyResolveResultSchema = resultSchema(
  resolvedHostDependencySchema,
  hostDependencyErrorSchema
);
export type HostDependencyResolveResult = Result<ResolvedHostDependency, HostDependencyError>;

export const hostDependencyViewResultSchema = resultSchema(
  hostDependencyViewSchema,
  hostDependencyErrorSchema
);
export type HostDependencyViewResult = Result<HostDependencyView, HostDependencyError>;

export interface HostDependencyResolver {
  resolve(id: DependencyId): Promise<HostDependencyResolveResult>;
}

export interface DependencyState {
  id: DependencyId;
  category: DependencyCategory;
  status: DependencyStatus;
  version: string | null;
  path: string | null;
  checkedAt: number;
  error?: string;
  latestVersion?: string | null;
  updateAvailable?: boolean;
}

export type DependencyStatusMap = Record<string, DependencyState>;

export type InstallCommandError =
  | {
      type: 'permission-denied';
      message: string;
      output: string;
      exitCode?: number | null;
      canRetryWithSudo?: boolean;
      elevatedCommand?: string;
      interactiveCommand?: string;
      command?: string;
    }
  | { type: 'command-failed'; message: string; output: string; exitCode?: number | null }
  | { type: 'pty-open-failed'; message: string };

export type DependencyInstallError =
  | { type: 'unknown-dependency'; id: string }
  | { type: 'no-install-command'; id: string }
  | { type: 'installer-missing'; id: string; tool: string; method: InstallMethod }
  | InstallCommandError
  | { type: 'not-detected-after-install'; id: string; output?: string };

export type DependencyInstallResult = Result<DependencyState, DependencyInstallError>;

export type DependencyUpdateError =
  | { type: 'unknown-dependency'; id: string }
  | { type: 'no-update-strategy'; id: string }
  | InstallCommandError
  | { type: 'not-detected-after-update'; id: string };

export type DependencyUpdateResult = Result<DependencyState, DependencyUpdateError>;

export type DependencyUninstallError =
  | { type: 'unknown-dependency'; id: string }
  | { type: 'no-uninstall-strategy'; id: string }
  | { type: 'no-uninstall-command'; id: string }
  | { type: 'still-present'; id: string }
  | InstallCommandError;

export type DependencyUninstallResult = Result<DependencyState, DependencyUninstallError>;

export type InstallOverride = NonNullable<HostDependencySelection>;

export type SelectedSource = { kind: 'auto' } | InstallOverride;

export type Installation = {
  id: string;
  realpath: string;
  pathEntry: string | null;
  isActive: boolean;
  manageable: false;
  status: DependencyStatus;
  version: string | null;
  latestVersion: string | null;
  updateAvailable: boolean;
};

export type HostDependency = {
  hostId: string;
  dependencyId: DependencyId;
  installations: Installation[];
  used: SelectedSource;
};

export type DependencyStatusUpdatedEvent = {
  id: string;
  state: DependencyState;
  connectionId?: string;
  hostDependency?: HostDependency;
};

export interface DependencyDescriptor {
  id: DependencyId;
  name: string;
  category: DependencyCategory;
  /** Binary names to try in order; first success wins. */
  commands: string[];
  docUrl?: string;
  updateCommand?: z.output<typeof hostDependencyUpdateCommandSchema>;
  status?: 'active' | 'deprecated';
}

export type DependencyProbeOptions = {
  refreshShellEnv?: boolean;
};

export type HostDependencyRunOptions = {
  run?: (command: string) => Promise<Result<void, InstallCommandError>>;
};

export interface HostDependencyManagerPort {
  readonly platform: Platform;
  initialize(): void;
  getAll(): Map<DependencyId, DependencyState>;
  get(id: DependencyId): DependencyState | undefined;
  getByCategory(cat: DependencyCategory): DependencyState[];
  getHostDependency(id: DependencyId): HostDependency | undefined;
  probe(id: DependencyId): Promise<DependencyState>;
  probeCategory(cat: DependencyCategory, options?: DependencyProbeOptions): Promise<void>;
}

export type { DependencyStatus, ProbeResult };
export type { Platform };

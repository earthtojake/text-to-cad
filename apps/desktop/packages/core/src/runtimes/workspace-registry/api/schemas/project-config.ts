import { z } from 'zod';
import { emdashScriptsConfigSchema } from '#primitives/emdash-config/api';

/**
 * The registry's config live model, projected per record: which scripts the
 * workspace's own `.emdash.json` defines and its preserve patterns — enough for the
 * desktop to render script availability without its own filesystem reads. Null until
 * the model's first read lands (boot and scans fill it off the blocking path).
 */
export const workspaceConfigSummarySchema = z.object({
  scripts: z.object({
    prepare: z.boolean(),
    setup: z.boolean(),
    run: z.boolean(),
    teardown: z.boolean(),
  }),
  preservePatterns: z.array(z.string()),
  /** True when the file exists but did not parse; the empty default applied. */
  parseError: z.boolean(),
});
export type WorkspaceConfigSummary = z.infer<typeof workspaceConfigSummarySchema>;

/**
 * Personal lifecycle settings stored on the repository record. Absence means inherit;
 * script tombstones are deliberately unsupported.
 */
export const personalProjectConfigSchema = z.object({
  preservePatterns: z.array(z.string()).optional(),
  scripts: emdashScriptsConfigSchema.optional(),
  autoRunSetup: z.boolean().optional(),
  autoRunRun: z.boolean().optional(),
});
export type PersonalProjectConfig = z.infer<typeof personalProjectConfigSchema>;

export const projectConfigProvenanceSchema = z.enum([
  'personal',
  'team',
  'host-default',
  'built-in',
]);
export type ProjectConfigProvenance = z.infer<typeof projectConfigProvenanceSchema>;

const resolvedStringProjectConfigFieldSchema = z.object({
  value: z.string(),
  from: projectConfigProvenanceSchema,
});

const resolvedBooleanProjectConfigFieldSchema = z.object({
  value: z.boolean(),
  from: projectConfigProvenanceSchema,
});

const resolvedStringArrayProjectConfigFieldSchema = z.object({
  value: z.array(z.string()),
  from: projectConfigProvenanceSchema,
});

export const resolvedProjectConfigSchema = z.object({
  preservePatterns: resolvedStringArrayProjectConfigFieldSchema,
  prepare: resolvedStringProjectConfigFieldSchema.optional(),
  setup: resolvedStringProjectConfigFieldSchema.optional(),
  run: resolvedStringProjectConfigFieldSchema.optional(),
  teardown: resolvedStringProjectConfigFieldSchema.optional(),
  shellSetup: resolvedStringProjectConfigFieldSchema.optional(),
  autoRunSetup: resolvedBooleanProjectConfigFieldSchema,
  autoRunRun: resolvedBooleanProjectConfigFieldSchema,
});
export type ResolvedProjectConfig = z.infer<typeof resolvedProjectConfigSchema>;

export const projectConfigSourceSchema = z.object({
  workspaceId: z.string().min(1),
  path: z.string().min(1),
  value: z.string(),
});
export type ProjectConfigSource = z.infer<typeof projectConfigSourceSchema>;

const projectConfigArraySourceSchema = projectConfigSourceSchema.extend({
  value: z.array(z.string()),
});

export const projectConfigSourcesSchema = z.object({
  preservePatterns: z.array(projectConfigArraySourceSchema),
  prepare: z.array(projectConfigSourceSchema),
  setup: z.array(projectConfigSourceSchema),
  run: z.array(projectConfigSourceSchema),
  teardown: z.array(projectConfigSourceSchema),
  shellSetup: z.array(projectConfigSourceSchema),
});
export type ProjectConfigSources = z.infer<typeof projectConfigSourcesSchema>;

export const projectConfigStateSchema = z.object({
  workspaceId: z.string().min(1),
  repositoryId: z.string().min(1),
  resolved: resolvedProjectConfigSchema,
  personalConfig: personalProjectConfigSchema,
  sources: projectConfigSourcesSchema,
  legacyDesktopSettingsMigrated: z.boolean(),
});
export type ProjectConfigState = z.infer<typeof projectConfigStateSchema>;

export const getProjectConfigInputSchema = z.object({
  workspaceId: z.string().min(1),
});
export type GetProjectConfigInput = z.infer<typeof getProjectConfigInputSchema>;

const personalProjectConfigPatchSchema = z.object({
  preservePatterns: z.array(z.string()).nullable().optional(),
  scripts: z
    .object({
      prepare: z.string().nullable().optional(),
      setup: z.string().nullable().optional(),
      run: z.string().nullable().optional(),
      teardown: z.string().nullable().optional(),
    })
    .optional(),
  autoRunSetup: z.boolean().nullable().optional(),
  autoRunRun: z.boolean().nullable().optional(),
});

export const patchPersonalProjectConfigInputSchema = z.object({
  workspaceId: z.string().min(1),
  patch: personalProjectConfigPatchSchema,
});
export type PatchPersonalProjectConfigInput = z.infer<typeof patchPersonalProjectConfigInputSchema>;

export const importLegacyLifecycleSettingsInputSchema = z.object({
  workspaceId: z.string().min(1),
  settings: personalProjectConfigSchema,
});
export type ImportLegacyLifecycleSettingsInput = z.infer<
  typeof importLegacyLifecycleSettingsInputSchema
>;

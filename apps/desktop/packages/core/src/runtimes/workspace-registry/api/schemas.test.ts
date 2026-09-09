import { describe, expect, it } from 'vitest';
import { emdashScriptsConfigSchema } from '#primitives/emdash-config/api';
import * as publicSchemas from './index';
import * as schemaBarrel from './schemas';
import { workspaceCreationSchema as creationWorkspaceCreationSchema } from './schemas/creation';
import { workspaceGitObservationsSchema as gitObservationWorkspaceGitObservationsSchema } from './schemas/git-observation';
import { workspaceLifecycleStepSchema as lifecycleStepsWorkspaceLifecycleStepSchema } from './schemas/lifecycle-steps';
import { updateWorktreeInputSchema as operationsUpdateWorktreeInputSchema } from './schemas/operations';
import { personalProjectConfigSchema as projectConfigPersonalProjectConfigSchema } from './schemas/project-config';
import { workspaceRecordSchema as recordsWorkspaceRecordSchema } from './schemas/records';
import { workspaceUsageSchema as usageWorkspaceUsageSchema } from './schemas/usage';

const { createWorktreeInputSchema } = schemaBarrel;

// Host-side validation of the createWorktree contract: baseRef is required unless
// gitSetup.fetchBranch materializes the branch instead (spec: pr-workspace-model
// provisioning). Callers never pass raw refspecs or config keys — the structured
// gitSetup block is the only crossing.

const base = {
  workspaceId: 'ws-1',
  repositoryId: 'repo-1',
  branch: 'pr/7/fix',
  path: '/tmp/wt',
};

describe('workspace registry schema exports', () => {
  it('preserves the public schema barrel across concept modules', () => {
    const conceptRoutes = [
      [
        publicSchemas.workspaceRecordSchema,
        schemaBarrel.workspaceRecordSchema,
        recordsWorkspaceRecordSchema,
      ],
      [
        publicSchemas.workspaceCreationSchema,
        schemaBarrel.workspaceCreationSchema,
        creationWorkspaceCreationSchema,
      ],
      [
        publicSchemas.workspaceLifecycleStepSchema,
        schemaBarrel.workspaceLifecycleStepSchema,
        lifecycleStepsWorkspaceLifecycleStepSchema,
      ],
      [
        publicSchemas.workspaceGitObservationsSchema,
        schemaBarrel.workspaceGitObservationsSchema,
        gitObservationWorkspaceGitObservationsSchema,
      ],
      [
        publicSchemas.personalProjectConfigSchema,
        schemaBarrel.personalProjectConfigSchema,
        projectConfigPersonalProjectConfigSchema,
      ],
      [
        publicSchemas.updateWorktreeInputSchema,
        schemaBarrel.updateWorktreeInputSchema,
        operationsUpdateWorktreeInputSchema,
      ],
      [
        publicSchemas.workspaceUsageSchema,
        schemaBarrel.workspaceUsageSchema,
        usageWorkspaceUsageSchema,
      ],
    ] as const;

    for (const [publicSchema, barrelSchema, conceptSchema] of conceptRoutes) {
      expect(publicSchema).toBe(conceptSchema);
      expect(barrelSchema).toBe(conceptSchema);
    }
  });

  it('parses personal scripts with the shared Emdash config schema', () => {
    const scripts = {
      prepare: 'pnpm install',
      setup: 'pnpm build',
      run: 'pnpm dev',
      teardown: 'pnpm clean',
      retiredKey: 'ignored',
    };

    expect(projectConfigPersonalProjectConfigSchema.parse({ scripts }).scripts).toEqual(
      emdashScriptsConfigSchema.parse(scripts)
    );
  });
});

describe('createWorktreeInputSchema', () => {
  it('accepts a plain baseRef input and applies defaults', () => {
    const parsed = createWorktreeInputSchema.parse({ ...base, baseRef: 'main' });
    expect(parsed).toEqual({
      ...base,
      baseRef: 'main',
      preservePatterns: [],
    });
  });

  it('preserves an explicit publication target', () => {
    const parsed = createWorktreeInputSchema.parse({
      ...base,
      baseRef: 'origin/main',
      publish: { remote: 'fork' },
    });
    expect(parsed.publish).toEqual({ remote: 'fork' });
  });

  it('accepts an omitted baseRef when gitSetup.fetchBranch is present', () => {
    const parsed = createWorktreeInputSchema.parse({
      ...base,
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/7/head' },
        upstream: { remote: 'origin', mergeRef: 'refs/pull/7/head' },
        breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/7' },
        followRef: true,
      },
    });
    expect(parsed.baseRef).toBeUndefined();
    expect(parsed.gitSetup?.followRef).toBe(true);
  });

  it('rejects an input with neither baseRef nor gitSetup.fetchBranch', () => {
    const result = createWorktreeInputSchema.safeParse({ ...base });
    expect(result.success).toBe(false);
  });

  it('rejects a gitSetup without fetchBranch when baseRef is also omitted', () => {
    const result = createWorktreeInputSchema.safeParse({
      ...base,
      gitSetup: { breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/7' } },
    });
    expect(result.success).toBe(false);
  });
});

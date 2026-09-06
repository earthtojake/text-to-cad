import {
  hostAbsolutePathSchema,
  portableRelativePathSchema,
} from '@emdash/core/primitives/path/api';
import { fileTreeModelSchema, fsErrorSchema } from '@emdash/core/runtimes/files/api';
import { projectConfigStateSchema } from '@emdash/core/runtimes/workspace-registry/api';
import type { Result } from '@emdash/shared';
import {
  defineContract,
  eventStream,
  fallible,
  liveJob,
  liveModel,
  liveState,
  mutation,
  procedure,
} from '@emdash/wire/rpc';
import z from 'zod';
import type {
  MigrateProjectConfigRequest,
  WriteProjectConfigRequest,
} from '@core/primitives/project-settings/api';
import {
  projectSchema,
  type CreateProjectParams,
  type CreateProjectResult,
  type InitializeRepositoryResult,
  type InspectProjectPathParams,
  type Project,
  type ProjectPlacementError,
  type ProjectPathInspection,
  type ResolveRepositoryDestinationParams,
} from '@core/primitives/projects/api';
import { mutationAckSchema, mutationErrorSchema } from '@core/primitives/wire/api/mutations';
import { projectAttachmentStateSchema, type ProjectRecoveryRequestError } from './attachments';
import type {
  MigrateProjectConfigResult,
  ProjectSettingsDomainPatch,
  ProjectSettingsError,
  ProjectSettingsPage,
} from './project-settings-page';

export const projectCreationErrorSchema = z.object({
  type: z.string(),
  message: z.string(),
});

export const projectCreationProgressSchema = z.object({
  phase: z.enum(['cloning', 'registering']),
  percent: z.number().int().min(0).max(100).optional(),
  message: z.string().optional(),
});

export const projectCreationStateSchema = z.discriminatedUnion('phase', [
  z.object({
    phase: z.literal('cloning'),
    message: z.string().optional(),
  }),
  z.object({
    phase: z.literal('registering'),
    message: z.string().optional(),
  }),
  z.object({
    phase: z.literal('ready'),
    project: projectSchema,
  }),
  z.object({
    phase: z.literal('error'),
    message: z.string(),
    error: projectCreationErrorSchema.optional(),
  }),
]);

export const projectCreationKeySchema = z.object({
  projectId: z.string(),
});

export const projectHostParamsSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('local') }),
  z.object({ type: z.literal('ssh'), connectionId: z.string().min(1) }),
]);

export const createProjectFromRemoteInputSchema = z.object({
  projectId: z.string(),
  host: projectHostParamsSchema,
  mode: z.enum(['clone', 'new']),
  repositoryUrl: z.string().min(1),
  targetPath: z.string().min(1),
  name: z.string().min(1),
});

export const projectDirectoryTreeKeySchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('local'),
    root: hostAbsolutePathSchema,
    sessionId: z.string(),
  }),
  z.object({
    type: z.literal('ssh'),
    connectionId: z.string().min(1),
    root: hostAbsolutePathSchema,
    sessionId: z.string(),
  }),
]);

const projectIdInputSchema = z.object({
  projectId: z.string(),
});

export type ProjectListData = {
  projects: Project[];
};

export const projectsDomain = 'projects' as const;

export const projectsWireContract = defineContract({
  createProject: procedure({
    input: z.custom<CreateProjectParams>(),
    output: z.custom<CreateProjectResult>(),
  }),
  inspectProjectPath: procedure({
    input: z.custom<InspectProjectPathParams>(),
    output: z.custom<ProjectPathInspection>(),
  }),
  initializeRepository: procedure({
    input: projectIdInputSchema,
    output: z.custom<InitializeRepositoryResult>(),
  }),
  getHostHomeDir: procedure({
    input: projectHostParamsSchema,
    output: z.string(),
  }),
  getDefaultRepositoriesRoot: procedure({
    input: projectHostParamsSchema,
    output: z.custom<Result<string, ProjectPlacementError>>(),
  }),
  ensureDefaultRepositoriesRoot: procedure({
    input: projectHostParamsSchema,
    output: z.custom<Result<string, ProjectPlacementError>>(),
  }),
  createHostDirectory: fallible({
    input: z.object({
      host: projectHostParamsSchema,
      root: hostAbsolutePathSchema,
      path: portableRelativePathSchema,
    }),
    data: z.void(),
    error: fsErrorSchema,
  }),
  resolveRepositoryDestination: procedure({
    input: z.custom<ResolveRepositoryDestinationParams>(),
    output: z.custom<Result<string, ProjectPlacementError>>(),
  }),
  deleteProject: procedure({
    input: projectIdInputSchema,
    output: z.void(),
  }),
  getProjectSettingsPage: procedure({
    input: projectIdInputSchema,
    output: z.custom<Result<ProjectSettingsPage, ProjectSettingsError>>(),
  }),
  updateProjectSettings: procedure({
    input: z.object({
      projectId: z.string(),
      patch: z.custom<ProjectSettingsDomainPatch>(),
    }),
    output: z.custom<Result<ProjectSettingsPage, ProjectSettingsError>>(),
  }),
  shareProjectSettingsToConfig: procedure({
    input: z.object({
      projectId: z.string(),
      request: z.custom<WriteProjectConfigRequest>(),
    }),
    output: z.custom<Result<ProjectSettingsPage, ProjectSettingsError>>(),
  }),
  migrateProjectConfig: procedure({
    input: z.object({
      projectId: z.string(),
      request: z.custom<MigrateProjectConfigRequest>(),
    }),
    output: z.custom<Result<MigrateProjectConfigResult, ProjectSettingsError>>(),
  }),
  countProjectsUsingGithubAccount: procedure({
    input: z.object({ accountId: z.string() }),
    output: z.number(),
  }),
  updateProjectConnection: procedure({
    input: z.object({ projectId: z.string(), connectionId: z.string() }),
    output: z.void(),
  }),
  recoverAttachment: procedure({
    input: projectIdInputSchema,
    output: z.custom<Result<void, ProjectRecoveryRequestError>>(),
  }),
  events: eventStream({
    key: z.void(),
    event: z.object({ type: z.literal('settings-changed'), projectId: z.string() }),
  }),
  projectList: liveModel({
    key: z.void(),
    states: {
      list: liveState({ data: z.custom<ProjectListData>() }),
    },
  }),
  attachments: liveModel({
    key: projectIdInputSchema,
    states: {
      state: liveState({ data: projectAttachmentStateSchema }),
    },
  }),
  projectConfig: liveModel({
    key: projectIdInputSchema,
    states: {
      current: liveState({ data: projectConfigStateSchema }),
    },
  }),
  creation: liveModel({
    key: projectCreationKeySchema,
    states: {
      state: liveState({ data: projectCreationStateSchema }),
    },
  }),
  directoryTree: liveModel({
    key: projectDirectoryTreeKeySchema,
    states: {
      tree: liveState({ data: fileTreeModelSchema }),
    },
    mutations: {
      expand: mutation({
        input: z.object({
          path: portableRelativePathSchema,
          depth: z.number().int().min(1).max(2).optional(),
        }),
        data: z.void(),
        error: fsErrorSchema,
      }),
      reveal: mutation({
        input: z.object({
          path: portableRelativePathSchema,
          depth: z.number().int().min(1).max(2).optional(),
        }),
        data: z.void(),
        error: fsErrorSchema,
      }),
    },
  }),
  create: liveJob({
    input: createProjectFromRemoteInputSchema,
    progress: projectCreationProgressSchema,
    result: projectSchema,
    error: projectCreationErrorSchema,
  }),
  delete: fallible({
    input: projectIdInputSchema,
    data: mutationAckSchema,
    error: mutationErrorSchema,
  }),
});

export type ProjectCreationState = z.infer<typeof projectCreationStateSchema>;
export type ProjectCreationJobError = z.infer<typeof projectCreationErrorSchema>;
export type ProjectCreationProgress = z.infer<typeof projectCreationProgressSchema>;
export type CreateProjectFromRemoteInput = z.infer<typeof createProjectFromRemoteInputSchema>;
export type ProjectHostParams = z.infer<typeof projectHostParamsSchema>;
export type ProjectsWireContract = typeof projectsWireContract;

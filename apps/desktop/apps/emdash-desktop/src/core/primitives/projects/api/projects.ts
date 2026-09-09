import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeResolveError } from '@emdash/core/primitives/runtime-resolution/api';
import type { Result } from '@emdash/shared';
import z from 'zod';

export function projectHostRef(project: Project): HostRef {
  return project.type === 'ssh' ? hostRef('remote', project.connectionId) : LOCAL_HOST_REF;
}

export type ProjectPathStatus = {
  isDirectory: boolean;
  isGitRepo: boolean;
  error?: { type: 'inspect-failed'; path: string; message: string } | RuntimeResolveError;
};

export const localProjectSchema = z.object({
  type: z.literal('local'),
  id: z.string(),
  name: z.string(),
  path: z.string(),
  /**
   * The branch detected at creation — immutable creation provenance only
   * (spec: github-git-settings §3). Never feeds resolution; null when the
   * project was created without a repository.
   */
  baseRef: z.string().nullable(),
  repositoryWorkspaceId: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const sshProjectSchema = z.object({
  type: z.literal('ssh'),
  id: z.string(),
  name: z.string(),
  path: z.string(),
  /** Creation provenance only; see `localProjectSchema.baseRef`. */
  baseRef: z.string().nullable(),
  connectionId: z.string(),
  repositoryWorkspaceId: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const projectSchema = z.discriminatedUnion('type', [localProjectSchema, sshProjectSchema]);

export type LocalProject = z.infer<typeof localProjectSchema>;
export type SshProject = z.infer<typeof sshProjectSchema>;
export type Project = z.infer<typeof projectSchema>;

export type CreateLocalProjectParams = {
  type: 'local';
  id?: string;
  path: string;
  name: string;
  initGitRepository?: boolean;
};

export type CreateSshProjectParams = {
  type: 'ssh';
  id?: string;
  name: string;
  path: string;
  connectionId: string;
  initGitRepository?: boolean;
};

export type CreateProjectParams = CreateLocalProjectParams | CreateSshProjectParams;

export type CreateProjectError =
  | { type: 'invalid-directory'; path: string; message: string }
  | { type: 'not-repository'; path: string }
  | { type: 'inspect-failed'; path: string; message: string }
  | { type: 'init-failed'; path: string; message: string }
  | { type: 'open-repository-failed'; path: string; message: string }
  | RuntimeResolveError;

export type CreateProjectResult = Result<Project, CreateProjectError>;

export type InitializeRepositoryError =
  | CreateProjectError
  | { type: 'project-not-found'; projectId: string; message: string };

export type InitializeRepositoryResult = Result<Project, InitializeRepositoryError>;

export type InspectLocalProjectPathParams = {
  type: 'local';
  path: string;
};

export type InspectSshProjectPathParams = {
  type: 'ssh';
  path: string;
  connectionId: string;
};

export type InspectProjectPathParams = InspectLocalProjectPathParams | InspectSshProjectPathParams;

export type ProjectPathInspection = ProjectPathStatus & {
  existingProject?: Project;
};

export type ProjectPlacementError =
  | RuntimeResolveError
  | { type: 'host-home-unavailable'; message: string }
  | { type: 'invalid-host-path'; path: string; message: string }
  | { type: 'filesystem-unavailable'; path: string; message: string };

export type ResolveRepositoryDestinationParams = {
  host: HostRef;
  name: string;
  chosenDir?: string;
};

export type UpdateProjectSettingsError =
  | { type: 'project-not-found' }
  | { type: 'invalid-settings' }
  | { type: 'invalid-worktree-directory' }
  | { type: 'write-config-failed'; message: string }
  | { type: 'error' };

export type ProjectRemoteState = {
  hasRemote: boolean;
  selectedRemoteUrl: string | null;
};

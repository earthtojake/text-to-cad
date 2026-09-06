import type { DataOf, ErrorOf, Result } from '@emdash/shared';
import type { ProjectAttachmentError } from '@core/features/projects/api';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';

export type ProjectAttachmentAccess = Pick<ProjectAttachmentManager, 'requireAttached'>;

export async function withAttachedProject<R extends Result<unknown, unknown>>(
  projects: ProjectAttachmentAccess,
  projectId: string,
  work: (project: ProjectProvider) => R | Promise<R>
): Promise<Result<DataOf<R>, ErrorOf<R> | ProjectAttachmentError>> {
  const attached = projects.requireAttached(projectId);
  if (!attached.success) return attached;
  return (await work(attached.data)) as Result<DataOf<R>, ErrorOf<R>>;
}

export function requireAttachedProjectOrThrow(
  projects: ProjectAttachmentAccess,
  projectId: string,
  toError: (error: ProjectAttachmentError) => Error = (error) => new Error(error.type)
): ProjectProvider {
  const attached = projects.requireAttached(projectId);
  if (!attached.success) throw toError(attached.error);
  return attached.data;
}

import { err } from '@emdash/shared';
import { and, eq, isNull } from 'drizzle-orm';
import { PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE } from '@core/features/projects/api/attachments';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import {
  archiveWorkspaceThroughRegistry,
  deleteWorkspaceThroughRegistry,
  type ArchiveWorkspaceInput,
  type WorkspaceRemovalBroker,
  type WorkspaceRemovalResult,
} from '@core/features/workspaces/api/node/operations/workspace-removal';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks } from '@core/services/app-db/node/schema';

export interface WorkspaceMutationOperations {
  delete(input: { workspaceId: string }): Promise<WorkspaceRemovalResult>;
  archive(input: ArchiveWorkspaceInput): Promise<WorkspaceRemovalResult>;
}

export type WorkspaceProjectResolver = (workspaceId: string) => Promise<string | undefined>;

export interface WorkspaceMutationServiceDependencies {
  db: AppDb;
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
  runtimes: WorkspaceRemovalBroker;
  projectIdForWorkspace?: WorkspaceProjectResolver;
}

export class WorkspaceMutationService implements WorkspaceMutationOperations {
  private readonly projectIdForWorkspace: WorkspaceProjectResolver;

  constructor(private readonly dependencies: WorkspaceMutationServiceDependencies) {
    this.projectIdForWorkspace =
      dependencies.projectIdForWorkspace ??
      ((workspaceId) => resolveProjectIdForWorkspace(dependencies.db, workspaceId));
  }

  async delete({ workspaceId }: { workspaceId: string }): Promise<WorkspaceRemovalResult> {
    const projectId = await this.projectIdForWorkspace(workspaceId);
    if (!projectId) {
      return err({
        type: 'project-missing',
        message: 'The Project for this workspace was not found.',
      });
    }
    const attached = this.dependencies.projects.requireAttached(projectId);
    if (!attached.success) return err(attachmentMutationError(attached.error.type));
    return deleteWorkspaceThroughRegistry(
      this.dependencies.db,
      this.dependencies.runtimes,
      workspaceId
    );
  }

  async archive(input: ArchiveWorkspaceInput): Promise<WorkspaceRemovalResult> {
    const attached = this.dependencies.projects.requireAttached(input.projectId);
    if (!attached.success) return err(attachmentMutationError(attached.error.type));
    return archiveWorkspaceThroughRegistry(this.dependencies.db, this.dependencies.runtimes, input);
  }
}

async function resolveProjectIdForWorkspace(
  db: AppDb,
  workspaceId: string
): Promise<string | undefined> {
  const [task] = await db
    .select({ projectId: tasks.projectId })
    .from(tasks)
    .where(and(eq(tasks.workspaceId, workspaceId), isNull(tasks.deletedAt)))
    .limit(1);
  return task?.projectId;
}

function attachmentMutationError(type: string): {
  type: 'project-missing' | 'project-unavailable';
  message: string;
} {
  return type === 'project-missing'
    ? { type: 'project-missing', message: 'Project was not found.' }
    : { type: 'project-unavailable', message: PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE };
}

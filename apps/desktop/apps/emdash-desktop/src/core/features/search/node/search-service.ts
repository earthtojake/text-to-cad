import type { HostAbsolutePath } from '@emdash/core/primitives/path/api';
import {
  isRuntimeResolveError,
  type HostRuntimesClient,
} from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import {
  createLiveJobReplicaCache,
  LiveJobFailedError,
  type LiveJobContext,
} from '@emdash/wire/live';
import { type JobError, type JobInput, type JobProgress, type JobResult } from '@emdash/wire/rpc';
import type Database from 'better-sqlite3';
import { and, eq, isNull } from 'drizzle-orm';
import { conversationEvents } from '@core/features/conversations/api/node/conversation-events';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import { projectEvents } from '@core/features/projects/api/node/project-events';
import type { TaskService } from '@core/features/tasks/api/node/task-service';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import type { WorkspaceRuntimeAccess } from '@core/features/workspaces/api/node/runtime-access';
import { getProvisionedWorkspaceBranch } from '@core/features/workspaces/api/node/workspace-branch';
import type { Conversation } from '@core/primitives/conversations/api';
import type { Project } from '@core/primitives/projects/api';
import type {
  PaletteEntitySearchQuery,
  SearchItem,
  WorkspaceFileHit,
} from '@core/primitives/search/api';
import type { Task } from '@core/primitives/tasks/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, tasks } from '@core/services/app-db/node/schema';
import { contentSearchRuntimeContract, type searchContract } from '../api';

type FtsRow = {
  item_type: string;
  item_id: string;
  project_id: string | null;
  task_id: string | null;
  title: string;
  keywords?: string;
  rank: number;
};

type RecentTaskRow = {
  id: string;
  name: string;
  project_id: string;
};

type RecentConversationRow = {
  id: string;
  title: string;
  project_id: string;
  task_id: string;
};

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, '\\$&');
}

export type SearchServiceDeps = {
  db: AppDb;
  sqlite: Database.Database;
  acquireWorkspaceRuntime(workspaceId: string): Promise<WorkspaceRuntimeAccess | null>;
  searchFileSearchRoot(
    client: HostRuntimesClient['fileSearch'],
    root: HostAbsolutePath,
    query: string,
    limit?: number
  ): Promise<WorkspaceFileHit[]>;
  getSearchExclusions(): Promise<readonly string[]>;
  tasks: Pick<TaskService, 'on'>;
};

export class SearchService {
  constructor(private readonly deps: SearchServiceDeps) {}

  initialize(): void {
    this.deps.tasks.on('task:created', (task) => void this.upsertTaskWithBranch(task));
    this.deps.tasks.on('task:updated', (task) => void this.upsertTaskWithBranch(task));
    this.deps.tasks.on('task:archived', (taskId) => this.removeByType('task', taskId));
    this.deps.tasks.on('task:deleted', (taskId) => this.removeByType('task', taskId));

    projectEvents.on('project:created', (project) => this.upsertProject(project));
    projectEvents.on('project:deleted', (projectId) => this.removeByType('project', projectId));

    conversationEvents.on('conversation:created', (conversation) =>
      this.upsertConversation(conversation)
    );
    conversationEvents.on('conversation:renamed', (conversationId, projectId, taskId, newTitle) => {
      this.upsertConversationById(conversationId, projectId, taskId, newTitle);
    });
    conversationEvents.on('conversation:deleted', (conversationId) =>
      this.removeByType('conversation', conversationId)
    );

    this.backfill();
  }

  async searchFiles(
    workspaceId: string,
    query: string,
    limit?: number
  ): Promise<WorkspaceFileHit[]> {
    const workspace = await this.deps.acquireWorkspaceRuntime(workspaceId);
    if (!workspace) return [];
    return await this.deps.searchFileSearchRoot(
      workspace.client.fileSearch,
      workspace.files.root,
      query,
      limit
    );
  }

  async searchContent(
    input: JobInput<typeof searchContract.searchWorkspaceContent>,
    context: LiveJobContext<JobProgress<typeof searchContract.searchWorkspaceContent>>
  ): Promise<
    Result<
      JobResult<typeof searchContract.searchWorkspaceContent>,
      JobError<typeof searchContract.searchWorkspaceContent>
    >
  > {
    let workspace: WorkspaceRuntimeAccess | null;
    try {
      workspace = await this.deps.acquireWorkspaceRuntime(input.workspaceId);
    } catch (error) {
      if (isRuntimeResolveError(error)) return err(error);
      throw error;
    }
    if (!workspace) {
      return err({
        type: 'workspace-not-found',
        workspaceId: input.workspaceId,
        message: `Workspace was not found: ${input.workspaceId}`,
      });
    }

    const jobs = createLiveJobReplicaCache(
      contentSearchRuntimeContract.searchContent,
      workspace.client.fileSearch.searchContent
    );
    const { workspaceId: _, ...searchInput } = input;
    try {
      const lease = await jobs.start({
        ...searchInput,
        root: workspace.files.root,
        exclusions: [...(await this.deps.getSearchExclusions())],
      });
      try {
        const job = await lease.ready();
        const unsubscribe = job.onProgress(context.progress);
        const cancel = () => void job.cancel();
        context.signal.addEventListener('abort', cancel, { once: true });
        if (context.signal.aborted) cancel();
        try {
          return ok(await job.result);
        } catch (error) {
          if (error instanceof LiveJobFailedError) return err(error.error);
          throw error;
        } finally {
          context.signal.removeEventListener('abort', cancel);
          unsubscribe();
        }
      } finally {
        await lease.release();
      }
    } finally {
      await jobs.dispose();
    }
  }

  async searchEntities({
    kind,
    query,
    context,
    limit = 50,
  }: PaletteEntitySearchQuery): Promise<SearchItem[]> {
    const trimmed = query.trim();
    const resultLimit = Math.max(1, Math.min(limit, 100));
    if (!trimmed) {
      return this.recents(context)
        .filter((item) => item.kind === kind)
        .slice(0, resultLimit);
    }
    const taskId = context?.taskId;
    if (kind === 'conversation' && !taskId) return [];

    try {
      const escaped = escapeLike(trimmed);
      const prefixPattern = `${escaped}%`;
      const substringPattern = `%${escaped}%`;
      const fuzzyPattern = `%${Array.from(trimmed).map(escapeLike).join('%')}%`;
      const rows = (
        kind === 'conversation'
          ? this.deps.sqlite
              .prepare(
                `SELECT item_type, item_id, project_id, task_id, title, keywords, 0 AS rank
                 FROM search_index
                 WHERE item_type = ? AND task_id = ?
                   AND (title LIKE ? ESCAPE '\\' OR keywords LIKE ? ESCAPE '\\')
                 ORDER BY CASE
                   WHEN lower(title) = lower(?) THEN 0
                   WHEN title LIKE ? ESCAPE '\\' THEN 1
                   WHEN title LIKE ? ESCAPE '\\' THEN 2
                   ELSE 3
                 END, length(title), title
                 LIMIT ?`
              )
              .all(
                kind,
                taskId,
                fuzzyPattern,
                fuzzyPattern,
                trimmed,
                prefixPattern,
                substringPattern,
                resultLimit
              )
          : this.deps.sqlite
              .prepare(
                `SELECT item_type, item_id, project_id, task_id, title, keywords, 0 AS rank
                 FROM search_index
                 WHERE item_type = ?
                   AND (title LIKE ? ESCAPE '\\' OR keywords LIKE ? ESCAPE '\\')
                 ORDER BY CASE
                   WHEN lower(title) = lower(?) THEN 0
                   WHEN title LIKE ? ESCAPE '\\' THEN 1
                   WHEN title LIKE ? ESCAPE '\\' THEN 2
                   ELSE 3
                 END, length(title), title
                 LIMIT ?`
              )
              .all(
                kind,
                fuzzyPattern,
                fuzzyPattern,
                trimmed,
                prefixPattern,
                substringPattern,
                resultLimit
              )
      ) as FtsRow[];

      return rows.map((row) => ({
        kind,
        id: row.item_id,
        projectId: row.project_id,
        taskId: row.task_id,
        title: row.title,
        subtitle: row.keywords ?? '',
        score: row.rank,
      }));
    } catch (error) {
      log.warn('SearchService: palette entity query failed', {
        kind,
        query,
        error: String(error),
      });
      return [];
    }
  }

  private recents(context?: PaletteEntitySearchQuery['context']): SearchItem[] {
    const taskStmt = context?.projectId
      ? this.deps.sqlite.prepare(
          `SELECT t.id, t.name, t.project_id
           FROM tasks t
           WHERE t.archived_at IS NULL AND t.deleted_at IS NULL AND t.project_id = ?
           ORDER BY t.last_interacted_at DESC
           LIMIT 10`
        )
      : this.deps.sqlite.prepare(
          `SELECT t.id, t.name, t.project_id
           FROM tasks t
           WHERE t.archived_at IS NULL AND t.deleted_at IS NULL
           ORDER BY t.last_interacted_at DESC
           LIMIT 10`
        );

    const taskRows = (
      context?.projectId ? taskStmt.all(context.projectId) : taskStmt.all()
    ) as RecentTaskRow[];

    const results: SearchItem[] = taskRows.map((r) => ({
      kind: 'task' as const,
      id: r.id,
      projectId: r.project_id,
      taskId: null,
      title: r.name,
      subtitle: '',
      score: 0,
    }));

    if (context?.taskId) {
      const conversationRows = this.deps.sqlite
        .prepare(
          `SELECT c.id, c.title, c.project_id, c.task_id
           FROM conversations c
           WHERE c.task_id = ?
           ORDER BY c.last_session_activity_at DESC
           LIMIT 10`
        )
        .all(context.taskId) as RecentConversationRow[];

      for (const r of conversationRows) {
        results.push({
          kind: 'conversation',
          id: r.id,
          projectId: r.project_id,
          taskId: r.task_id,
          title: r.title,
          subtitle: '',
          score: 0,
        });
      }
    }

    return results;
  }

  private async upsertTaskWithBranch(task: Task): Promise<void> {
    let branchName: string | undefined;
    if (task.workspaceId) {
      const [ws] = await this.deps.db
        .select({ kind: workspaces.kind, config: workspaces.config })
        .from(workspaces)
        .where(and(eq(workspaces.id, task.workspaceId), liveWorkspaces()))
        .limit(1);
      branchName = ws ? (getProvisionedWorkspaceBranch(ws) ?? undefined) : undefined;
    }
    this.upsertTask(task, branchName);
  }

  private upsertTask(task: Task, branchName?: string): void {
    const keywords = [branchName, task.linkedIssue?.identifier, task.linkedIssue?.title]
      .filter(Boolean)
      .join(' ');

    try {
      this.deps.sqlite
        .prepare(
          `INSERT OR REPLACE INTO search_index(item_type, item_id, project_id, task_id, title, keywords)
           VALUES ('task', ?, ?, NULL, ?, ?)`
        )
        .run(task.id, task.projectId, task.name, keywords);
    } catch (e) {
      log.warn('SearchService: upsertTask failed', { taskId: task.id, error: String(e) });
    }
  }

  private upsertProject(project: Project): void {
    try {
      this.deps.sqlite
        .prepare(
          `INSERT OR REPLACE INTO search_index(item_type, item_id, project_id, task_id, title, keywords)
           VALUES ('project', ?, NULL, NULL, ?, ?)`
        )
        .run(project.id, project.name, project.path);
    } catch (e) {
      log.warn('SearchService: upsertProject failed', {
        projectId: project.id,
        error: String(e),
      });
    }
  }

  private upsertConversation(conversation: Conversation): void {
    try {
      this.deps.sqlite
        .prepare(
          `INSERT OR REPLACE INTO search_index(item_type, item_id, project_id, task_id, title, keywords)
           VALUES ('conversation', ?, ?, ?, ?, '')`
        )
        .run(conversation.id, conversation.projectId, conversation.taskId, conversation.title);
    } catch (e) {
      log.warn('SearchService: upsertConversation failed', {
        conversationId: conversation.id,
        error: String(e),
      });
    }
  }

  private upsertConversationById(
    conversationId: string,
    projectId: string,
    taskId: string,
    title: string
  ): void {
    try {
      this.deps.sqlite
        .prepare(
          `INSERT OR REPLACE INTO search_index(item_type, item_id, project_id, task_id, title, keywords)
           VALUES ('conversation', ?, ?, ?, ?, '')`
        )
        .run(conversationId, projectId, taskId, title);
    } catch (e) {
      log.warn('SearchService: upsertConversationById failed', {
        conversationId,
        error: String(e),
      });
    }
  }

  private removeByType(itemType: string, itemId: string): void {
    try {
      this.deps.sqlite
        .prepare(`DELETE FROM search_index WHERE item_id = ? AND item_type = ?`)
        .run(itemId, itemType);
    } catch (e) {
      log.warn('SearchService: removeByType failed', { itemType, itemId, error: String(e) });
    }
  }

  private backfill(): void {
    try {
      const count = (
        this.deps.sqlite.prepare(`SELECT count(*) as n FROM search_index`).get() as { n: number }
      ).n;

      if (count > 0) return;

      const allTasks = this.deps.db
        .select({
          id: tasks.id,
          projectId: tasks.projectId,
          name: tasks.name,
          archivedAt: tasks.archivedAt,
          linkedIssue: tasks.linkedIssue,
          workspaceKind: workspaces.kind,
          workspaceConfig: workspaces.config,
        })
        .from(tasks)
        .leftJoin(workspaces, and(eq(tasks.workspaceId, workspaces.id), liveWorkspaces()))
        .where(isNull(tasks.deletedAt))
        .all();
      const allProjects = this.deps.db
        .select({ id: projects.id, name: projects.name, path: workspaces.path })
        .from(projects)
        .leftJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
        .where(isNull(projects.deletedAt))
        .all();
      const allConversations = this.deps.db.select().from(conversations).all();

      const upsertStmt = this.deps.sqlite.prepare(
        `INSERT OR REPLACE INTO search_index(item_type, item_id, project_id, task_id, title, keywords)
         VALUES (?, ?, ?, ?, ?, ?)`
      );

      this.deps.sqlite.transaction(() => {
        for (const t of allTasks) {
          if (t.archivedAt) continue;
          const branchName = getProvisionedWorkspaceBranch({
            kind: t.workspaceKind,
            config: t.workspaceConfig,
          });
          const keywords = [branchName, t.linkedIssue?.identifier, t.linkedIssue?.title]
            .filter(Boolean)
            .join(' ');
          upsertStmt.run('task', t.id, t.projectId, null, t.name, keywords);
        }
        for (const p of allProjects) {
          upsertStmt.run('project', p.id, null, null, p.name, p.path ?? '');
        }
        for (const c of allConversations) {
          upsertStmt.run('conversation', c.id, c.projectId, c.taskId, c.title, '');
        }
      })();

      log.info('SearchService: backfilled search index', {
        tasks: allTasks.filter((t) => !t.archivedAt).length,
        projects: allProjects.length,
        conversations: allConversations.length,
      });
    } catch (e) {
      log.warn('SearchService: backfill failed', { error: String(e) });
    }
  }
}

export function createSearchService(deps: SearchServiceDeps): SearchService {
  return new SearchService(deps);
}

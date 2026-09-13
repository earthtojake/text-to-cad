import { computed, makeAutoObservable, observable, reaction, runInAction } from 'mobx';
import { type ProjectStore } from '@core/features/projects/api/browser/stores/project';
import type { ProjectManagerStore } from '@core/features/projects/api/browser/stores/project-manager';
import { asAvailableProject } from '@core/features/projects/api/browser/stores/project-selectors';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { taskManagerStoreToken } from '@core/features/tasks/contributions/browser/project-store-tokens';
import {
  workbenchSidebarMemento,
  type WorkbenchSidebarState,
} from '@core/features/workbench/contributions/mementos';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import {
  registeredTaskData,
  unregisteredTaskData,
} from '@core/primitives/task-state/browser/task-state';
export type SidebarTaskSortBy = WorkbenchSidebarState['taskSortBy'];

export type TaskSortKind = 'created' | 'updated';

export function sortKindFor(sortBy: SidebarTaskSortBy): TaskSortKind {
  return sortBy === 'created-at' ? 'created' : 'updated';
}

export function getSortInstant(task: TaskStore, kind: TaskSortKind): string | undefined {
  const reg = registeredTaskData(task);
  if (reg) {
    if (kind === 'created') return reg.createdAt;
    return reg.lastInteractedAt ?? reg.updatedAt;
  }
  const u = unregisteredTaskData(task);
  if (u) {
    if (kind === 'created') return u.createdAt;
    return u.lastInteractedAt;
  }
  return undefined;
}

function isVisibleRegularTask(task: TaskStore): boolean {
  return (
    task.data.type !== 'automation-run' &&
    (task.state === 'unregistered' || !('archivedAt' in task.data && task.data.archivedAt))
  );
}

export type SidebarRow =
  | { kind: 'project'; projectId: string }
  | { kind: 'task'; projectId: string; taskId: string };

export class SidebarStore {
  private _handle: MementoHandle<WorkbenchSidebarState> | undefined;
  private _fallbackState: WorkbenchSidebarState = workbenchSidebarMemento.default;

  constructor(private readonly projectManager: ProjectManagerStore) {
    // `_handle` must stay observable: computeds reading `state` before the
    // memento handle is attached would otherwise capture zero dependencies
    // and freeze at the fallback value forever.
    makeAutoObservable<SidebarStore, '_fallbackState' | '_handle' | 'projectManager'>(this, {
      _fallbackState: false,
      _handle: observable.ref,
      projectManager: false,
      expandedProjectIds: computed.struct,
      sidebarRows: computed,
      pinnedSidebarEntries: computed,
    });

    // Auto-expand a project when its task count goes from 0 to >0.
    const prevTaskCounts = new Map<string, number>();
    reaction(
      () => {
        const counts: [string, number][] = [];
        for (const [id, project] of this.projectManager.projects) {
          const context = asAvailableProject(project);
          if (context) {
            counts.push([id, context.get(taskManagerStoreToken).tasks.size]);
          }
        }
        return counts;
      },
      (counts) => {
        runInAction(() => {
          for (const [id, count] of counts) {
            const prev = prevTaskCounts.get(id) ?? 0;
            if (prev === 0 && count > 0) {
              this.ensureProjectExpanded(id);
            }
            prevTaskCounts.set(id, count);
          }
        });
      }
    );
  }

  get projectOrder(): string[] {
    return this.state.projectOrder;
  }

  get taskOrderByProject(): Record<string, string[]> {
    return this.state.taskOrderByProject;
  }

  get expandedProjectIds(): ReadonlySet<string> {
    return new Set(this.state.expandedProjectIds);
  }

  get taskSortBy(): SidebarTaskSortBy {
    return this.state.taskSortBy;
  }

  attachMemento(handle: MementoHandle<WorkbenchSidebarState>): void {
    if (this._handle) throw new Error('Sidebar memento is already attached');
    this._handle = handle;
  }

  get orderedProjects(): ProjectStore[] {
    const all = Array.from(this.projectManager.projects.values());

    return [...all].sort((a, b) => {
      const ai = this.projectOrder.indexOf(a.id);
      const bi = this.projectOrder.indexOf(b.id);
      if (ai === -1 && bi === -1) return this.compareSidebarProjects(a, b);
      if (ai === -1) return -1;
      if (bi === -1) return 1;
      return ai - bi;
    });
  }

  get sidebarRows(): SidebarRow[] {
    const rows: SidebarRow[] = [];
    for (const project of this.orderedProjects) {
      const projectId = project.id;
      rows.push({ kind: 'project', projectId });
      const context = asAvailableProject(project);
      if (this.expandedProjectIds.has(projectId) && context) {
        const tasks = Array.from(context.get(taskManagerStoreToken).tasks.values()).filter(
          isVisibleRegularTask
        );
        const manualOrder = this.taskOrderByProject[projectId];
        const ordered = manualOrder?.length
          ? this.mergeTaskOrder(projectId, tasks)
          : this.sortTasksForSidebar(tasks);
        for (const task of ordered) {
          if (task.data.isPinned) continue;
          rows.push({ kind: 'task', projectId, taskId: task.data.id });
        }
      }
    }
    return rows;
  }

  /** Visible unpinned tasks in the same order they are rendered in the project tree. */
  get visibleTaskEntries(): { projectId: string; taskId: string }[] {
    return this.sidebarRows
      .filter((row): row is Extract<SidebarRow, { kind: 'task' }> => row.kind === 'task')
      .map(({ projectId, taskId }) => ({ projectId, taskId }));
  }

  /** Flat list of pinned tasks from available Project contexts, in project-tree sort order. */
  get pinnedSidebarEntries(): { projectId: string; taskId: string }[] {
    const pairs: { projectId: string; task: TaskStore }[] = [];
    for (const project of this.projectManager.projects.values()) {
      const context = asAvailableProject(project);
      if (!context) continue;
      const projectId = project.id;
      for (const task of context.get(taskManagerStoreToken).tasks.values()) {
        if (!isVisibleRegularTask(task) || !task.data.isPinned) continue;
        pairs.push({ projectId, task });
      }
    }
    pairs.sort((a, b) => this.compareSidebarTasks(a.task, b.task));
    return pairs.map(({ projectId, task }) => ({ projectId, taskId: task.data.id }));
  }

  /**
   * Visible unpinned task IDs for a project in sidebar order. Archived tasks are
   * and automation tasks are excluded. Independent of expand state so Next/Previous
   * Task navigation works even when the project is collapsed.
   */
  visibleTaskIdsForProject(projectId: string): string[] {
    const project = this.projectManager.projects.get(projectId);
    if (!project) return [];
    const context = asAvailableProject(project);
    if (!context) return [];
    const tasks = Array.from(context.get(taskManagerStoreToken).tasks.values()).filter(
      (task) => isVisibleRegularTask(task) && !task.data.isPinned
    );
    const manualOrder = this.taskOrderByProject[projectId];
    const ordered = manualOrder?.length
      ? this.mergeTaskOrder(projectId, tasks)
      : this.sortTasksForSidebar(tasks);
    return ordered.map((t) => t.data.id);
  }

  get isEmpty(): boolean {
    return this.projectManager.projects.size === 0;
  }

  /** Called on first load when no snapshot exists — expand all known projects. */
  expandAllProjects(): void {
    this.updateState((current) => ({
      ...current,
      expandedProjectIds: this.orderedProjects.map((project) => project.id),
    }));
  }

  toggleProjectExpanded(projectId: string): void {
    if (this.expandedProjectIds.has(projectId)) {
      this.updateExpandedProjects((ids) => ids.filter((id) => id !== projectId));
    } else {
      this.updateExpandedProjects((ids) => [...ids, projectId]);
    }
  }

  ensureProjectExpanded(projectId: string): void {
    if (!this.expandedProjectIds.has(projectId)) {
      this.updateExpandedProjects((ids) => [...ids, projectId]);
    }
  }

  setTaskSortBy(sortBy: SidebarTaskSortBy): void {
    this.updateState((current) => ({ ...current, taskSortBy: sortBy }));
  }

  /** Set the sort key and clear all manual task orders so the list fully re-sorts. */
  applySort(sortBy: SidebarTaskSortBy): void {
    this.updateState((current) => ({
      ...current,
      taskSortBy: sortBy,
      taskOrderByProject: {},
    }));
  }

  setProjectOrder(ids: string[]): void {
    this.updateState((current) => ({ ...current, projectOrder: ids }));
  }

  mergeTaskOrder(projectId: string, tasks: TaskStore[]): TaskStore[] {
    const stored = this.taskOrderByProject[projectId] ?? [];
    const byId = new Map(tasks.map((t) => [t.data.id, t] as const));
    const seen = new Set<string>();
    const result: TaskStore[] = [];
    for (const id of stored) {
      const t = byId.get(id);
      if (t) {
        result.push(t);
        seen.add(id);
      }
    }
    // New tasks (not in the manual order) are sorted by date and prepended so
    // they always appear at the top rather than buried after manually-ordered tasks.
    const newTasks = tasks
      .filter((t) => !seen.has(t.data.id))
      .sort((a, b) => this.compareSidebarTasks(a, b));
    return [...newTasks, ...result];
  }

  setTaskOrder(projectId: string, orderedIds: string[]): void {
    this.updateState((current) => ({
      ...current,
      taskOrderByProject: { ...current.taskOrderByProject, [projectId]: orderedIds },
    }));
  }

  private get state(): WorkbenchSidebarState {
    return this._handle?.value ?? this._fallbackState;
  }

  private updateState(update: (current: WorkbenchSidebarState) => WorkbenchSidebarState): void {
    if (this._handle) {
      this._handle.update(update);
    } else {
      this._fallbackState = update(this._fallbackState);
    }
  }

  private updateExpandedProjects(update: (current: string[]) => string[]): void {
    this.updateState((current) => ({
      ...current,
      expandedProjectIds: update(current.expandedProjectIds),
    }));
  }

  private compareSidebarTasks(a: TaskStore, b: TaskStore): number {
    const kind = sortKindFor(this.taskSortBy);
    const ia = getSortInstant(a, kind) ?? '';
    const ib = getSortInstant(b, kind) ?? '';
    const d = ib.localeCompare(ia);
    if (d !== 0) return d;
    return a.data.id.localeCompare(b.data.id);
  }

  private compareSidebarProjects(a: ProjectStore, b: ProjectStore): number {
    const d = b.createdAt.localeCompare(a.createdAt);
    if (d !== 0) return d;
    return a.id.localeCompare(b.id);
  }

  private sortTasksForSidebar(tasks: TaskStore[]): TaskStore[] {
    return [...tasks].sort((a, b) => this.compareSidebarTasks(a, b));
  }
}

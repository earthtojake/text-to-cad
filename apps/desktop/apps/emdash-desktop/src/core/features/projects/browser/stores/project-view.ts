import type { ExternalSelectionStore } from '@emdash/ui/react/patterns';
import { makeAutoObservable } from 'mobx';
import type * as React from 'react';
import type {
  ProjectTaskSortBy,
  ProjectViewState,
} from '@core/features/projects/contributions/mementos';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';
import type { MementoHandle } from '@core/primitives/mementos/browser';

export type ProjectView = 'tasks' | 'pull-request' | 'workspaces' | 'settings';

export class ProjectViewStore {
  readonly taskView: TaskViewStore;

  constructor(private readonly handle: MementoHandle<ProjectViewState>) {
    this.taskView = new TaskViewStore(handle);
    makeAutoObservable<ProjectViewStore, 'handle'>(this, { handle: false, taskView: false });
  }

  get activeView(): ProjectView {
    return this.handle.value.activeView;
  }

  get selectedIssueProvider(): LinkedIssue['provider'] | null {
    return (this.handle.value.selectedIssueProvider as LinkedIssue['provider'] | undefined) ?? null;
  }

  setProjectView(view: ProjectView) {
    this.handle.update((current) => ({ ...current, activeView: view }));
  }

  setSelectedIssueProvider(provider: LinkedIssue['provider'] | null) {
    this.handle.update((current) => ({
      ...current,
      selectedIssueProvider: provider ?? undefined,
    }));
  }
}

/**
 * Task-list view state. Selection implements the list-view framework's
 * `ExternalSelectionStore`, so `CollectionView` rows delegate selection here
 * while this store stays the app-wide source of truth (bulk bar, delete
 * command). Shift-clicks arrive through `toggle` with the original event; the
 * range they select follows the list's visible order, injected via
 * `attachOrderedIds` because this store outlives any single list view.
 */
export class TaskViewStore implements ExternalSelectionStore {
  selectedIds: Set<string> = new Set();
  private anchorId: string | null = null;
  private getOrderedIds: (() => string[]) | null = null;

  constructor(private readonly handle: MementoHandle<ProjectViewState>) {
    makeAutoObservable<TaskViewStore, 'handle' | 'getOrderedIds'>(this, {
      handle: false,
      getOrderedIds: false,
    });
  }

  get tab(): 'active' | 'archived' {
    return this.handle.value.taskViewTab;
  }

  get sortBy(): ProjectTaskSortBy {
    return this.handle.value.taskSortBy ?? 'updated-at';
  }

  setTab(tab: 'active' | 'archived') {
    this.handle.update((current) => ({ ...current, taskViewTab: tab }));
  }

  setSortBy(sortBy: ProjectTaskSortBy) {
    this.handle.update((current) => ({ ...current, taskSortBy: sortBy }));
  }

  /** Wires in the list view's visible row order; shift-ranges follow it. */
  attachOrderedIds(getOrderedIds: () => string[]) {
    this.getOrderedIds = getOrderedIds;
  }

  get count(): number {
    return this.selectedIds.size;
  }

  isSelected(id: string): boolean {
    return this.selectedIds.has(id);
  }

  toggle(id: string, e?: React.MouseEvent | React.KeyboardEvent) {
    const isShift = e !== undefined && 'shiftKey' in e && e.shiftKey;
    if (isShift && this.anchorId && this.anchorId !== id) {
      this.selectRange(this.anchorId, id, this.getOrderedIds?.() ?? []);
      return;
    }
    if (this.selectedIds.has(id)) {
      this.selectedIds.delete(id);
    } else {
      this.selectedIds.add(id);
    }
    this.anchorId = id;
  }

  selectRange(fromId: string, toId: string, orderedIds: string[]) {
    const fromIndex = orderedIds.indexOf(fromId);
    const toIndex = orderedIds.indexOf(toId);
    if (fromIndex === -1 || toIndex === -1) {
      this.toggle(toId);
      return;
    }
    const [start, end] = fromIndex < toIndex ? [fromIndex, toIndex] : [toIndex, fromIndex];
    this.selectedIds = new Set(orderedIds.slice(start, end + 1));
  }

  selectAll(orderedIds: string[]) {
    this.selectedIds = new Set(orderedIds);
    this.anchorId = null;
  }

  clear() {
    this.selectedIds = new Set();
    this.anchorId = null;
  }
}

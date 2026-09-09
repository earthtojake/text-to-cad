import { makeAutoObservable, observable, reaction } from 'mobx';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import type { TaskComposition } from '@core/features/workbench/api/browser/task-composition';
import { registeredTaskData } from '@core/primitives/task-state/browser/task-state';

type TaskCompositionFactory = (workspaceId: string) => TaskComposition;

/**
 * Stable task-scoped owner for the workspace-bound TaskComposition.
 *
 * The handle exists for optimistic tasks, while the composition is created only
 * after the task receives its authoritative workspace identity.
 */
export class TaskCompositionHandle {
  current: TaskComposition | null = null;

  private _activated = false;
  private _disposed = false;
  private _stopObserving: (() => void) | null = null;

  constructor(
    task: TaskStore,
    private readonly _create: TaskCompositionFactory
  ) {
    makeAutoObservable<
      TaskCompositionHandle,
      '_activated' | '_create' | '_disposed' | '_stopObserving'
    >(
      this,
      {
        current: observable.ref,
        _activated: false,
        _create: false,
        _disposed: false,
        _stopObserving: false,
      },
      { autoBind: true }
    );

    this._stopObserving = reaction(
      () => registeredTaskData(task)?.workspaceId ?? null,
      this.replace,
      { fireImmediately: true }
    );
  }

  async ready(): Promise<void> {
    await this.current?.space.ready;
  }

  activate(): void {
    if (this._activated || this._disposed) return;
    this._activated = true;
    this.current?.activate();
  }

  dispose(): void {
    if (this._disposed) return;
    this._disposed = true;
    this._stopObserving?.();
    this._stopObserving = null;
    this.replace(null);
  }

  private replace(workspaceId: string | null): void {
    const previous = this.current;
    this.current = null;
    previous?.dispose();

    if (!workspaceId || this._disposed) return;

    const next = this._create(workspaceId);
    this.current = next;
    if (this._activated) next.activate();
  }
}

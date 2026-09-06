import { log } from '@emdash/shared/logger';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';
import type { Project } from '@core/primitives/projects/api';

export type ProjectCrudHooks = {
  'project:created': (project: Project) => void | Promise<void>;
  'project:deleted': (projectId: string) => void | Promise<void>;
};

class ProjectEvents implements Hookable<ProjectCrudHooks> {
  private readonly _core = new HookCore<ProjectCrudHooks>((name, e) =>
    log.error(`ProjectEvents: ${String(name)} hook error`, { error: e })
  );

  on<K extends keyof ProjectCrudHooks>(name: K, handler: ProjectCrudHooks[K]) {
    return this._core.on(name, handler);
  }

  _emit<K extends keyof ProjectCrudHooks>(name: K, ...args: Parameters<ProjectCrudHooks[K]>): void {
    this._core.callHookBackground(name, ...args);
  }
}

export const projectEvents = new ProjectEvents();

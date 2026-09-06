import { observable } from 'mobx';
import { getProjectHostAccess } from '@core/features/projects/api/browser/stores/project-selectors';
import { TerminalManagerStore } from '@core/features/terminals/api/browser/task-terminal/terminal-manager';

export class TerminalRegistry {
  private readonly entries = observable.map<string, TerminalManagerStore>();

  acquire(taskId: string, projectId: string): TerminalManagerStore {
    const existing = this.entries.get(taskId);
    if (existing) return existing;
    const store = new TerminalManagerStore(projectId, taskId, getProjectHostAccess(projectId));
    this.entries.set(taskId, store);
    return store;
  }

  get(taskId: string): TerminalManagerStore | undefined {
    return this.entries.get(taskId);
  }

  release(taskId: string): void {
    const store = this.entries.get(taskId);
    if (!store) return;
    store.dispose();
    this.entries.delete(taskId);
  }
}

export const terminalRegistry = new TerminalRegistry();

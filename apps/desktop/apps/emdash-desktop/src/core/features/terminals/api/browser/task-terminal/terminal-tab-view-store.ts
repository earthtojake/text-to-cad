import { action, comparer, computed, makeObservable, reaction } from 'mobx';
import type { TaskTerminalSelectionState } from '@core/features/tasks/contributions/mementos';
import type {
  TerminalManagerStore,
  TerminalStore,
} from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import { type TabViewProvider } from '@core/primitives/workbench-shell/browser/tabs/generic-tab-view';
import {
  reorderTabIds,
  setNextTabActive,
  setPreviousTabActive,
  setTabActive,
  setTabActiveIndex,
} from '@core/primitives/workbench-shell/browser/tabs/tab-utils';

export class TerminalTabViewStore implements TabViewProvider<TerminalStore, never> {
  private readonly _getResource: () => TerminalManagerStore | null;
  private readonly disposers: (() => void)[] = [];

  constructor(
    private readonly handle: MementoHandle<TaskTerminalSelectionState>,
    getResource: () => TerminalManagerStore | null
  ) {
    this._getResource = getResource;
    makeObservable<TerminalTabViewStore, 'handle' | 'syncTerminalIds'>(this, {
      tabOrder: computed,
      activeTabId: computed,
      tabs: computed,
      activeTab: computed,
      addTab: action,
      removeTab: action,
      reorderTabs: action,
      setNextTabActive: action,
      setPreviousTabActive: action,
      setTabActiveIndex: action,
      setActiveTab: action,
      syncTerminalIds: action,
      handle: false,
    });

    this.disposers.push(
      reaction(
        () => {
          const resource = this._getResource();
          return {
            isLoaded: resource?.isLoaded ?? false,
            ids: Array.from(resource?.terminals.keys() ?? []),
          };
        },
        action(({ isLoaded, ids }) => {
          if (!isLoaded) return;
          this.syncTerminalIds(ids);
        }),
        { fireImmediately: true, equals: comparer.structural }
      )
    );
  }

  get tabOrder(): string[] {
    return this.handle.value.tabOrder;
  }

  get activeTabId(): string | undefined {
    return this.handle.value.activeTabId;
  }

  get tabs(): TerminalStore[] {
    const resource = this._getResource();
    if (!resource) return [];
    return this.tabOrder.map((id) => resource.terminals.get(id)).filter(Boolean) as TerminalStore[];
  }

  get activeTab(): TerminalStore | undefined {
    return this.activeTabId ? this._getResource()?.terminals.get(this.activeTabId) : undefined;
  }

  setActiveTab(id: string): void {
    this.updateSelection((selection) => setTabActive(selection, id));
  }

  reorderTabs(fromIndex: number, toIndex: number): void {
    this.updateSelection((selection) => reorderTabIds(selection, fromIndex, toIndex));
  }

  setNextTabActive(): void {
    this.updateSelection(setNextTabActive);
  }

  setPreviousTabActive(): void {
    this.updateSelection(setPreviousTabActive);
  }

  setTabActiveIndex(index: number): void {
    this.updateSelection((selection) => setTabActiveIndex(selection, index));
  }

  // addTab is required by TabViewProvider but terminals are created explicitly
  addTab(_args: never): void {}

  removeTab(id: string): void {
    void this._getResource()?.deleteTerminal(id);
  }

  closeActiveTab(): void {
    if (this.activeTabId) this.removeTab(this.activeTabId);
  }

  dispose(): void {
    for (const d of this.disposers) d();
  }

  private syncTerminalIds(ids: string[]): void {
    const idSet = new Set(ids);
    this.updateSelection((selection) => {
      selection.tabOrder = selection.tabOrder.filter((id) => idSet.has(id));
      for (const id of ids) {
        if (!selection.tabOrder.includes(id)) selection.tabOrder.push(id);
      }
      if (selection.activeTabId && !idSet.has(selection.activeTabId)) {
        selection.activeTabId = selection.tabOrder[0];
      }
      if (!selection.activeTabId && selection.tabOrder.length > 0) {
        selection.activeTabId = selection.tabOrder[0];
      }
    });
  }

  private updateSelection(
    update: (selection: { tabOrder: string[]; activeTabId: string | undefined }) => void
  ): void {
    this.handle.update((current) => {
      const selection = {
        tabOrder: [...current.tabOrder],
        activeTabId: current.activeTabId,
      };
      update(selection);
      return { ...current, ...selection };
    });
  }
}

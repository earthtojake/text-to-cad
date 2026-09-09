export interface TabOrderState {
  tabOrder: string[];
  activeTabId: string | undefined;
}

export function addTabId(state: TabOrderState, id: string): void {
  if (!state.tabOrder.includes(id)) {
    state.tabOrder.push(id);
  }
}

export function removeTabId(state: TabOrderState, id: string): void {
  const idx = state.tabOrder.indexOf(id);
  if (idx === -1) return;
  state.tabOrder.splice(idx, 1);
  if (state.activeTabId === id) {
    state.activeTabId = state.tabOrder[idx] ?? state.tabOrder[idx - 1];
  }
}

export function setTabActive(state: TabOrderState, id: string): void {
  state.activeTabId = id;
}

export function reorderTabIds(state: TabOrderState, fromIndex: number, toIndex: number): void {
  if (fromIndex === toIndex) return;
  const [tab] = state.tabOrder.splice(fromIndex, 1);
  state.tabOrder.splice(toIndex, 0, tab);
}

export function setNextTabActive(state: TabOrderState): void {
  if (!state.activeTabId || state.tabOrder.length === 0) return;
  const activeIndex = state.tabOrder.indexOf(state.activeTabId);
  if (activeIndex === -1) return;
  state.activeTabId = state.tabOrder[(activeIndex + 1) % state.tabOrder.length];
}

export function setPreviousTabActive(state: TabOrderState): void {
  if (!state.activeTabId || state.tabOrder.length === 0) return;
  const activeIndex = state.tabOrder.indexOf(state.activeTabId);
  if (activeIndex === -1) return;
  state.activeTabId =
    state.tabOrder[(activeIndex - 1 + state.tabOrder.length) % state.tabOrder.length];
}

export function setTabActiveIndex(state: TabOrderState, index: number): void {
  if (index < 0 || state.tabOrder.length === 0) return;
  if (index >= state.tabOrder.length) {
    state.activeTabId = state.tabOrder[state.tabOrder.length - 1];
  } else {
    state.activeTabId = state.tabOrder[index];
  }
}

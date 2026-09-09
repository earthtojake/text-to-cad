export interface TabViewProvider<TEntity, TArgs> {
  removeTab: (tabId: string) => void;
  addTab: (args: TArgs) => void;
  reorderTabs: (fromIndex: number, toIndex: number) => void;
  setNextTabActive: () => void;
  setPreviousTabActive: () => void;
  setTabActiveIndex: (index: number) => void;
  setActiveTab: (id: string) => void;
  activeTabId: string | undefined;
  activeTab: TEntity | undefined;
  tabs: TEntity[];
}

export type TabViewSnapshot = {
  tabOrder: string[];
  activeTabId: string | undefined;
};

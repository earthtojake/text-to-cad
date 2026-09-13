import React, { createContext, useContext } from 'react';

type SettingsSearchState = {
  query: string;
  setQuery: (query: string) => void;
};

const EMPTY_STATE: SettingsSearchState = { query: '', setQuery: () => {} };

const SettingsSearchContext = createContext<SettingsSearchState>(EMPTY_STATE);

export function SettingsSearchProvider({
  query,
  setQuery,
  children,
}: {
  query: string;
  setQuery: (query: string) => void;
  children: React.ReactNode;
}) {
  const value = React.useMemo(
    () => ({ query: query.trim() ? query : '', setQuery }),
    [query, setQuery]
  );
  return <SettingsSearchContext.Provider value={value}>{children}</SettingsSearchContext.Provider>;
}

export function useSettingsSearch(): SettingsSearchState {
  return useContext(SettingsSearchContext);
}

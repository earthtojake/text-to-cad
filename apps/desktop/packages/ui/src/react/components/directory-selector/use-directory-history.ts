import * as React from 'react';

export interface DirectoryHistoryState {
  readonly entries: readonly string[];
  readonly index: number;
}

export interface DirectoryHistory {
  readonly path: string;
  readonly backPath: string | null;
  readonly forwardPath: string | null;
  readonly canGoBack: boolean;
  readonly canGoForward: boolean;
  navigate(path: string): void;
  back(): void;
  forward(): void;
}

export function createDirectoryHistoryState(initialPath: string): DirectoryHistoryState {
  return { entries: [initialPath], index: 0 };
}

export function pushDirectoryHistory(
  state: DirectoryHistoryState,
  path: string
): DirectoryHistoryState {
  if (state.entries[state.index] === path) return state;
  return {
    entries: [...state.entries.slice(0, state.index + 1), path],
    index: state.index + 1,
  };
}

export function goBackDirectoryHistory(state: DirectoryHistoryState): DirectoryHistoryState {
  if (state.index === 0) return state;
  return { ...state, index: state.index - 1 };
}

export function goForwardDirectoryHistory(state: DirectoryHistoryState): DirectoryHistoryState {
  if (state.index >= state.entries.length - 1) return state;
  return { ...state, index: state.index + 1 };
}

export function useDirectoryHistory(initialPath: string): DirectoryHistory {
  const [state, setState] = React.useState(() => createDirectoryHistoryState(initialPath));

  React.useEffect(() => {
    setState(createDirectoryHistoryState(initialPath));
  }, [initialPath]);

  const path = state.entries[state.index] ?? initialPath;

  return {
    path,
    backPath: state.index > 0 ? (state.entries[state.index - 1] ?? null) : null,
    forwardPath:
      state.index < state.entries.length - 1 ? (state.entries[state.index + 1] ?? null) : null,
    canGoBack: state.index > 0,
    canGoForward: state.index < state.entries.length - 1,
    navigate: React.useCallback((nextPath: string) => {
      setState((current) => pushDirectoryHistory(current, nextPath));
    }, []),
    back: React.useCallback(() => {
      setState(goBackDirectoryHistory);
    }, []),
    forward: React.useCallback(() => {
      setState(goForwardDirectoryHistory);
    }, []),
  };
}

import type { Terminal } from '@xterm/xterm';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  collectTerminalSearchMatches,
  getNextTerminalSearchIndex,
  type TerminalSearchBufferLike,
  type TerminalSearchMatch,
} from '@core/features/terminals/browser/pty/terminal-search';

export type TerminalSearchStatus = {
  found: boolean;
  currentIndex: number;
  total: number;
};

const EMPTY_SEARCH_STATUS: TerminalSearchStatus = {
  found: false,
  currentIndex: 0,
  total: 0,
};

interface UseTerminalSearchOptions {
  terminal: Terminal | null | undefined;
  enabled: boolean;
  onCloseFocus?: () => void;
}

export function useTerminalSearch({ terminal, enabled, onCloseFocus }: UseTerminalSearchOptions) {
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchedTerminalRef = useRef<Terminal | null>(null);
  const activeSearchQueryRef = useRef('');
  const activeSearchMatchRef = useRef<TerminalSearchMatch | null>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchStatus, setSearchStatus] = useState<TerminalSearchStatus>(EMPTY_SEARCH_STATUS);

  const resetSearchState = useCallback(() => {
    setSearchQuery('');
    setSearchStatus(EMPTY_SEARCH_STATUS);
    setIsSearchOpen(false);
  }, []);

  const clearTerminalSelection = useCallback((target?: Terminal | null) => {
    const candidate = target ?? searchedTerminalRef.current;
    if (!candidate) return;
    try {
      candidate.clearSelection();
    } catch {}
    if (candidate === searchedTerminalRef.current) {
      searchedTerminalRef.current = null;
      activeSearchQueryRef.current = '';
      activeSearchMatchRef.current = null;
    }
  }, []);

  const runTerminalSearch = useCallback(
    (
      query: string,
      options: {
        direction?: 'next' | 'prev';
        reset?: boolean;
      } = {}
    ): TerminalSearchStatus => {
      if (!enabled || !terminal) {
        setSearchStatus(EMPTY_SEARCH_STATUS);
        return EMPTY_SEARCH_STATUS;
      }

      if (searchedTerminalRef.current && searchedTerminalRef.current !== terminal) {
        clearTerminalSelection(searchedTerminalRef.current);
      }

      if (!query) {
        clearTerminalSelection(terminal);
        setSearchStatus(EMPTY_SEARCH_STATUS);
        return EMPTY_SEARCH_STATUS;
      }

      const buffer = terminal.buffer?.active as TerminalSearchBufferLike | undefined;
      if (!buffer) {
        searchedTerminalRef.current = terminal;
        activeSearchQueryRef.current = query;
        activeSearchMatchRef.current = null;
        setSearchStatus(EMPTY_SEARCH_STATUS);
        return EMPTY_SEARCH_STATUS;
      }

      const matches = collectTerminalSearchMatches(buffer, query);
      if (matches.length === 0) {
        searchedTerminalRef.current = terminal;
        activeSearchQueryRef.current = query;
        activeSearchMatchRef.current = null;
        try {
          terminal.clearSelection();
        } catch {}
        setSearchStatus(EMPTY_SEARCH_STATUS);
        return EMPTY_SEARCH_STATUS;
      }

      const direction = options.direction ?? 'next';
      const currentMatch =
        !options.reset && activeSearchQueryRef.current === query
          ? activeSearchMatchRef.current
          : null;
      const matchIndex = getNextTerminalSearchIndex(matches, currentMatch, direction);
      const match = matches[matchIndex];

      searchedTerminalRef.current = terminal;
      activeSearchQueryRef.current = query;
      activeSearchMatchRef.current = match;

      try {
        terminal.select(match.col, match.row, match.length);
        const contextRows = Math.max(0, Math.floor(terminal.rows / 2));
        terminal.scrollToLine(Math.max(0, match.row - contextRows));
      } catch {}

      const result = {
        found: true,
        currentIndex: matchIndex + 1,
        total: matches.length,
      };
      setSearchStatus(result);
      return result;
    },
    [clearTerminalSelection, enabled, terminal]
  );

  const closeSearch = useCallback(() => {
    clearTerminalSelection();
    resetSearchState();
    onCloseFocus?.();
  }, [clearTerminalSelection, onCloseFocus, resetSearchState]);

  const openSearch = useCallback(() => {
    if (!enabled) return;
    setIsSearchOpen(true);
  }, [enabled]);

  const handleSearchQueryChange = useCallback(
    (nextQuery: string) => {
      setSearchQuery(nextQuery);
      if (!nextQuery) {
        clearTerminalSelection();
        setSearchStatus(EMPTY_SEARCH_STATUS);
        return;
      }
      runTerminalSearch(nextQuery, { direction: 'next', reset: true });
    },
    [clearTerminalSelection, runTerminalSearch]
  );

  const stepSearch = useCallback(
    (direction: 'next' | 'prev') => {
      if (!searchQuery) return;
      runTerminalSearch(searchQuery, { direction, reset: false });
    },
    [runTerminalSearch, searchQuery]
  );

  useEffect(() => {
    if (!isSearchOpen) return;
    const id = requestAnimationFrame(() => {
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    });
    return () => cancelAnimationFrame(id);
  }, [isSearchOpen]);

  useEffect(() => {
    if (enabled || !isSearchOpen) return;
    const id = requestAnimationFrame(() => {
      clearTerminalSelection();
      resetSearchState();
      onCloseFocus?.();
    });
    return () => cancelAnimationFrame(id);
  }, [clearTerminalSelection, enabled, isSearchOpen, onCloseFocus, resetSearchState]);

  useEffect(() => {
    if (searchedTerminalRef.current && searchedTerminalRef.current !== terminal) {
      const id = requestAnimationFrame(() => {
        clearTerminalSelection(searchedTerminalRef.current);
        setSearchStatus(EMPTY_SEARCH_STATUS);
      });
      return () => cancelAnimationFrame(id);
    }
  }, [clearTerminalSelection, terminal]);

  useEffect(() => {
    if (!enabled || !isSearchOpen || !searchQuery || !terminal) return;
    const id = requestAnimationFrame(() => {
      runTerminalSearch(searchQuery, { direction: 'next', reset: true });
    });
    return () => cancelAnimationFrame(id);
  }, [enabled, isSearchOpen, runTerminalSearch, searchQuery, terminal]);

  useEffect(() => {
    return () => clearTerminalSelection();
  }, [clearTerminalSelection]);

  return {
    isSearchOpen,
    searchQuery,
    searchStatus,
    searchInputRef,
    openSearch,
    closeSearch,
    handleSearchQueryChange,
    stepSearch,
  };
}

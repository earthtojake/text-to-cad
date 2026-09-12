/**
 * Settings search, done by the rows themselves.
 *
 * Codex's settings search finds a row on a page you are not looking at, which
 * means the search has to know every row on every page. The obvious way to do
 * that is an index — a list of `{page, title, description}` — and the obvious
 * problem with an index is that it is a second copy of every row's text, free
 * to drift from the row it claims to describe.
 *
 * So there is no index. While a query is active every page is mounted, each row
 * decides for itself whether it matches, and cards and pages that end up with
 * no matching rows hide themselves. The searchable text is the text on screen
 * because it is the same string.
 */
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import type { SettingsSection } from "@renderer/state/ui";

/**
 * Every term has to appear somewhere in the row's text. `worktree delete`
 * therefore finds "Auto-delete old worktrees" without the words being adjacent,
 * which is how someone who half-remembers a setting types.
 */
export function matchesQuery(query: string, ...fields: (string | undefined)[]): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystack = fields.filter(Boolean).join(" ").toLowerCase();
  return needle.split(/\s+/).every((term) => haystack.includes(term));
}

/* -------------------------------------------------------------------------- */

type RowReport = (id: string, matched: boolean) => void;

type SearchValue = {
  query: string;
  /** The section being rendered, so a card's report can be counted per page. */
  section: SettingsSection;
  /** A card reporting whether any of its rows matched. */
  reportCard: RowReport;
};

const SearchContext = createContext<SearchValue | null>(null);
/** Rows report to their card; cards aggregate. */
const CardContext = createContext<RowReport | null>(null);

export function SettingsSearchProvider({
  query,
  section,
  reportCard,
  children,
}: SearchValue & { children: React.ReactNode }) {
  const value = useMemo(
    () => ({ query, section, reportCard }),
    [query, section, reportCard],
  );
  return <SearchContext.Provider value={value}>{children}</SearchContext.Provider>;
}

export function CardMatchProvider({
  report,
  children,
}: {
  report: RowReport;
  children: React.ReactNode;
}) {
  return <CardContext.Provider value={report}>{children}</CardContext.Provider>;
}

/** The active query, or `""` outside a search (and in a unit test). */
export function useSettingsQuery(): string {
  return useContext(SearchContext)?.query ?? "";
}

export function useCardReport(): RowReport {
  const report = useContext(CardContext);
  return report ?? noop;
}

export function useSectionReport(): { section: SettingsSection; report: RowReport } {
  const context = useContext(SearchContext);
  return {
    section: context?.section ?? "general",
    report: context?.reportCard ?? noop,
  };
}

function noop() {}

/* -------------------------------------------------------------------------- */

/**
 * A set of ids that reported a match, and the reporter that maintains it.
 *
 * Used by cards (whose members are rows) and by the route (whose members are
 * cards). The setter compares before it writes, so a row reporting the same
 * answer twice does not schedule a render.
 */
export function useMatchSet(): { anyMatched: boolean; matched: Set<string>; report: RowReport } {
  const [matched, setMatched] = useState<Set<string>>(() => new Set());

  const report = useCallback((id: string, isMatch: boolean) => {
    setMatched((current) => {
      if (current.has(id) === isMatch) {
        return current;
      }
      const next = new Set(current);
      if (isMatch) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }, []);

  return { anyMatched: matched.size > 0, matched, report };
}

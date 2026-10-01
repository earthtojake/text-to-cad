import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Search } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import { ScrollArea } from "@renderer/components/ui/scroll-area";
import { SettingsPage } from "@renderer/features/settings/pages";
import { SettingsSearchProvider } from "@renderer/features/settings/search";
import { noteSessions, seedSessions, useWorktreeCache } from "@renderer/features/settings/worktree-cache";
import { useSessions } from "@renderer/state/sessions";
import {
  SETTINGS_SECTIONS,
  SETTINGS_SECTION_LABELS,
  useUi,
  type SettingsSection,
} from "@renderer/state/ui";

/**
 * Settings replaces the whole window (plan §3): back to the app, a search box,
 * grouped nav on the left, one page on the right.
 *
 * A full-window route rather than a modal because these pages have their own
 * navigation and their own search — a dialog would be fighting the shell for
 * the keyboard the entire time it is open.
 *
 * Searching switches the right-hand side from one page to all seven, stacked,
 * with everything that does not match removed. That is what makes a query find
 * a row on a page you were not looking at without a hand-maintained index of
 * every row's text (`./search.tsx`).
 */
export function SettingsRoute() {
  const section = useUi((state) => state.settingsSection);
  const setSection = useUi((state) => state.setSettingsSection);
  const close = useUi((state) => state.closeSettings);
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";

  // The worktree lists are kept for this visit (`worktree-cache.ts`): a session
  // opening, closing or moving changes a row's "in use" (status churn does
  // not), and closing Settings drops them.
  useEffect(() => {
    seedSessions(useSessions.getState().sessions);
    const off = window.textToCad.on("sessions.changed", noteSessions);
    return () => {
      off();
      useWorktreeCache.getState().clear();
    };
  }, []);

  // Which sections have a card that matched, so the nav can drop the ones that
  // did not, and how many rows each card matched, for the status line. Cards
  // report; a section with no reports has nothing to show.
  //
  // Cards report by a `useId` that is stable for as long as they are mounted,
  // so a card that stops matching says so, and a card that unmounts withdraws
  // its match (`SettingCard`). The unprefixed entries written while no query
  // is active are not about a search at all, and `isSection` discards those.
  const [matches, setMatches] = useState<Record<string, number>>({});
  const reportCard = useCallback((id: string, rows: number) => {
    setMatches((current) => (current[id] === rows ? current : { ...current, [id]: rows }));
  }, []);

  const matchedSections = useMemo(() => {
    const found = new Set<SettingsSection>();
    for (const [id, rows] of Object.entries(matches)) {
      const candidate = id.split("|")[0];
      // Reports made while not searching are unprefixed; they are about a card
      // that is not part of this query and are not a section name either.
      if (rows > 0 && isSection(candidate)) {
        found.add(candidate);
      }
    }
    return found;
  }, [matches]);

  // How many rows the query matched, for the status line: the page below is seven pages
  // stacked, and a count is the one thing that says whether the typing found anything.
  // Rows, not cards: a card is a group of rows and "sound" finds three in one.
  const matchedRows = Object.entries(matches).reduce(
    (total, [id, rows]) => (isSection(id.split("|")[0]) && id.includes("|") ? total + rows : total),
    0,
  );

  const navSections = searching
    ? SETTINGS_SECTIONS.filter((candidate) => matchedSections.has(candidate))
    : SETTINGS_SECTIONS;

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground">
      {/* Settings replaces the shell, so this bar is the window's top-left:
          it reserves the traffic lights' room itself, the same way the
          leftmost pane does (globals.css). */}
      <header
        className="app-drag flex shrink-0 items-center gap-3 px-3"
        data-settings-header
        style={{
          height: "var(--titlebar-height)",
          paddingLeft: "calc(var(--titlebar-inset) + 0.75rem)",
        }}
      >
        <Button
          className="app-no-drag h-7 gap-1.5 px-2 text-xs"
          onClick={close}
          size="sm"
          variant="ghost"
        >
          <ArrowLeft className="size-3.5" />
          Back to app
        </Button>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav aria-label="Settings" className="flex w-[232px] shrink-0 flex-col gap-2 border-r px-3 py-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            {/* `pl-8!`, not `pl-8`: `cn` keeps the vendored Input's `px-3`
                beside it (different properties), and in the built sheet
                `px-3` lands later and wins, putting the glyph over the text. */}
            <Input
              aria-label="Search settings"
              autoFocus
              className="h-8 pl-8! text-sm"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search settings"
              value={query}
            />
          </div>
          <div className="flex flex-col gap-0.5">
            {navSections.map((candidate) => (
              <NavItem
                active={!searching && candidate === section}
                key={candidate}
                label={SETTINGS_SECTION_LABELS[candidate]}
                onSelect={() => {
                  setSection(candidate);
                  setQuery("");
                }}
              />
            ))}
            {/* One live region, there before the first keystroke so the count is announced.
                Nothing matching is said on the page; a count is for the ear. */}
            <p
              className={cn(searching && matchedRows === 0 ? "px-2 py-3 text-xs text-muted-foreground" : "sr-only")}
              role="status"
            >
              {!searching ? "" : matchedRows === 0 ? "No matching settings." : `${matchedRows} ${matchedRows === 1 ? "row matches" : "rows match"}`}
            </p>
          </div>
        </nav>

        <ScrollArea className="min-h-0 flex-1">
          <main className="mx-auto w-full max-w-[720px] px-8 py-8">
            {searching ? (
              <>
                {/* The page's one h1 while searching; each page's heading is an h2 under it. */}
                <h1 className="sr-only">Search results</h1>
                {SETTINGS_SECTIONS.map((candidate) => (
                  <SearchedSection
                    hidden={!matchedSections.has(candidate)}
                    key={candidate}
                    query={query}
                    reportCard={reportCard}
                    section={candidate}
                  />
                ))}
              </>
            ) : (
              <SettingsSearchProvider query="" reportCard={reportCard} section={section}>
                <h1 className="mb-6 text-xl font-semibold tracking-tight">
                  {SETTINGS_SECTION_LABELS[section]}
                </h1>
                <SettingsPage section={section} />
              </SettingsSearchProvider>
            )}
          </main>
        </ScrollArea>
      </div>
    </div>
  );
}

/**
 * One page inside a search. Mounted whether or not it matched — a page that
 * unmounted could not report that it now matches — and hidden when it did not.
 */
function SearchedSection({
  section,
  query,
  hidden,
  reportCard,
}: {
  section: SettingsSection;
  query: string;
  hidden: boolean;
  reportCard: (id: string, rows: number) => void;
}) {
  // Cards report by their own `useId`, which is unique per tree; prefixing with
  // the section is what lets the route count matches per page.
  const report = useCallback(
    (id: string, rows: number) => reportCard(`${section}|${id}`, rows),
    [reportCard, section],
  );

  return (
    <section hidden={hidden}>
      <h2 className="mb-6 text-xl font-semibold tracking-tight">
        {SETTINGS_SECTION_LABELS[section]}
      </h2>
      <SettingsSearchProvider query={query} reportCard={report} section={section}>
        <SettingsPage section={section} />
      </SettingsSearchProvider>
    </section>
  );
}

function isSection(value: string | undefined): value is SettingsSection {
  return SETTINGS_SECTIONS.includes(value as SettingsSection);
}

function NavItem({
  label,
  active,
  onSelect,
}: {
  label: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={cn(
        "rounded-md px-2 py-1.5 text-left text-[13px] transition-colors",
        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60",
      )}
      // The page on screen, said as well as tinted.
      aria-current={active ? "page" : undefined}
      onClick={onSelect}
      type="button"
    >
      {label}
    </button>
  );
}

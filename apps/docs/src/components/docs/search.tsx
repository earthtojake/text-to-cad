"use client";

import { CornerDownLeft, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { Dialog } from "radix-ui";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchRecord } from "@/lib/docs/source";
import { cn } from "@/lib/utils";

/**
 * The documentation's search: a dialog (the button, Ctrl or Command with K, or `/`) over an index
 * the site builds, `/docs/search.json`: every page cut at its headings. It is fetched the first time
 * the dialog opens and searched in the browser; nothing is sent anywhere.
 */

type Indexed = SearchRecord & { title: string; lowHeading: string; lowText: string };
type Result = { record: Indexed; score: number; snippet: string };

const RESULTS = 12;

function snippetOf(text: string, low: string, token: string) {
  const at = low.indexOf(token);
  if (at < 0) return text.slice(0, 140);
  const start = Math.max(0, at - 50);
  return `${start ? "..." : ""}${text.slice(start, start + 150).trim()}${start + 150 < text.length ? "..." : ""}`;
}

// Every word of the query must be in a part of a page; a match in the page's name counts for most,
// one in the part's heading for less, one in its text for least.
function search(records: Indexed[], query: string): Result[] {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const results: Result[] = [];
  for (const record of records) {
    let score = record.heading ? 0 : 2;
    let matched = true;
    for (const token of tokens) {
      const inTitle = record.title.includes(token);
      const inHeading = record.lowHeading.includes(token);
      const inText = record.lowText.includes(token);
      if (!inTitle && !inHeading && !inText) {
        matched = false;
        break;
      }
      score += (inTitle ? (record.title.startsWith(token) ? 10 : 7) : 0) + (inHeading ? 6 : 0) + (inText ? 1 : 0);
    }
    if (matched) {
      const token = tokens.find((word) => record.lowText.includes(word)) ?? tokens[0];
      results.push({ record, score, snippet: snippetOf(record.text, record.lowText, token) });
    }
  }
  return results.sort((a, b) => b.score - a.score).slice(0, RESULTS);
}

// `shortcut`: this one answers the keys. A page has two buttons (the sidebar's and the phone bar's) and one
// of them listens, so the keys open one dialog.
export function DocsSearch({ className, shortcut = false }: { className?: string; shortcut?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [records, setRecords] = useState<Indexed[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(0);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement && (event.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName));
      if ((event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) || (event.key === "/" && !typing)) {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcut]);

  useEffect(() => {
    if (!open || records) return;
    let stale = false;
    fetch("/docs/search.json")
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((loaded: SearchRecord[]) => {
        if (stale) return;
        setRecords(
          loaded.map((record) => ({
            ...record,
            title: record.page.toLowerCase(),
            lowHeading: record.heading.toLowerCase(),
            lowText: record.text.toLowerCase(),
          })),
        );
      })
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [open, records]);

  const results = useMemo(() => (records ? search(records, query) : []), [records, query]);
  const chosen = Math.min(active, Math.max(results.length - 1, 0));

  const go = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = event.key === "ArrowDown" ? Math.min(chosen + 1, results.length - 1) : Math.max(chosen - 1, 0);
      setActive(next);
      list.current?.children[next]?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && results[chosen]) {
      event.preventDefault();
      go(results[chosen].record.href);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          aria-label="Search the documentation"
          className={cn(
            "inline-flex h-8 cursor-pointer items-center gap-2 rounded-lg border border-border bg-background text-sm text-muted-foreground outline-none transition hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring dark:bg-input/30",
            "w-full justify-between px-2.5",
            className,
          )}
        >
          <span className="inline-flex items-center gap-2">
            <Search className="size-4 shrink-0" aria-hidden="true" />
            Search
          </span>
          {shortcut ? (
            <kbd className="rounded border border-border px-1 font-mono text-[10px] leading-4" aria-hidden="true">
              /
            </kbd>
          ) : null}
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-[12svh] left-1/2 z-50 flex max-h-[70svh] w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-lg outline-none"
        >
          <Dialog.Title className="sr-only">Search the documentation</Dialog.Title>
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              placeholder="Search the docs"
              aria-label="Search the docs"
              role="combobox"
              aria-expanded={results.length > 0}
              aria-controls="docs-search-results"
              aria-activedescendant={results[chosen] ? `docs-search-${chosen}` : undefined}
              className="h-11 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
            />
            <kbd className="rounded border border-border px-1.5 font-mono text-[10px] leading-4 text-muted-foreground">Esc</kbd>
          </div>
          <ul ref={list} id="docs-search-results" role="listbox" aria-label="Results" className="min-h-0 flex-1 overflow-y-auto p-1.5 empty:hidden">
            {results.map(({ record, snippet }, index) => (
              <li key={record.href} id={`docs-search-${index}`} role="option" aria-selected={index === chosen}>
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => go(record.href)}
                  onMouseMove={() => setActive(index)}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-left",
                    index === chosen && "bg-secondary",
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">
                      {record.page}
                      {record.heading ? <span className="font-normal text-muted-foreground"> › {record.heading}</span> : null}
                    </span>
                    <span className="block truncate text-xs leading-5 text-muted-foreground">{snippet || record.section}</span>
                  </span>
                  {index === chosen ? <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
                </button>
              </li>
            ))}
          </ul>
          {results.length ? null : (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground" role="status">
              {failed
                ? "The search index did not load. Reload the page to try again."
                : !records
                  ? "Loading..."
                  : query.trim()
                    ? `Nothing found for "${query.trim()}".`
                    : "Search the guides, the document types, the integrations and the reference."}
            </p>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

import { DiffEditor } from "@monaco-editor/react";
import {
  ChevronDown,
  ChevronRight,
  GitCommitHorizontal,
  GitCompare,
  RotateCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@renderer/components/ui/popover";
import { Spinner } from "@renderer/components/ui/spinner";
import { Textarea } from "@renderer/components/ui/textarea";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { cn } from "@renderer/lib/utils";
import { useExplorer } from "@renderer/state/explorer";
import type { ReviewTab as ReviewTabModel } from "@shared/types";
import type { Project } from "@shared/types";

import { EmptyState } from "./EmptyState";
import { FileIcon } from "./icons";
import { SHARED_EDITOR_OPTIONS, languageFor, monacoTheme } from "./monaco";
import { setupMonaco } from "./monaco-setup";
import type { ChangedFile, FileDiff, GitStatus } from "./types";

/**
 * The review: what changed, as stacked per-file diffs with a rail of the files
 * on the right — Codex's layout, and the same one as the file tab, so the two
 * feel like one pane with two contents.
 *
 * Each file's diff is fetched when its section first opens, not up front: a
 * turn that touched forty files would otherwise be forty `git show` pairs
 * before the header could draw, and the header is the part someone is looking
 * at first.
 *
 * The diffs are Monaco's diff editor in **inline** mode, which is what Codex
 * shows and what fits: a side-by-side diff in a 45%-wide pane is two columns
 * of forty characters each.
 */

const SCOPE_LABELS: Record<ReviewTabModel["scope"], string> = {
  all: "All changes",
  "1h": "Since an hour ago",
  "4h": "Since four hours ago",
  "24h": "Since yesterday",
  "7d": "Since last week",
};

const STATUS_BADGES: Record<ChangedFile["status"], { letter: string; className: string }> = {
  added: { letter: "A", className: "text-emerald-600 dark:text-emerald-400" },
  untracked: { letter: "A", className: "text-emerald-600 dark:text-emerald-400" },
  modified: { letter: "M", className: "text-amber-600 dark:text-amber-400" },
  renamed: { letter: "R", className: "text-sky-600 dark:text-sky-400" },
  deleted: { letter: "D", className: "text-rose-600 dark:text-rose-400" },
};

/**
 * The scope is the review's identity: changing it changes every answer on the
 * page — the totals, the file list, each file's two sides. So it is a `key`
 * rather than a dependency, and the body below starts each scope from its own
 * initial state instead of clearing four pieces of the previous one.
 */
export function ReviewTab(props: {
  tabId: string;
  project: Project;
  scope: ReviewTabModel["scope"];
}) {
  return <ReviewBody key={`${props.project.id}:${props.scope}`} {...props} />;
}

function ReviewBody({
  tabId,
  project,
  scope,
}: {
  tabId: string;
  project: Project;
  scope: ReviewTabModel["scope"];
}) {
  const update = useExplorer((state) => state.update);

  const [status, setStatus] = useState<GitStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sections = useRef(new Map<string, HTMLElement>());

  const read = useCallback(
    (openTop: boolean) =>
      window.hardcore.git
        .status({ projectId: project.id, scope: scopeFor(scope) })
        .catch(() => null)
        .then((next) => {
          setStatus(next);
          setLoading(false);
          if (openTop) {
            // The first few files open by default: a review whose sections are
            // all shut is a list of filenames, which is not a review.
            setOpen(new Set((next?.files ?? []).slice(0, 3).map((file) => file.path)));
          }
        }),
    [project.id, scope],
  );

  useEffect(() => {
    void read(true);
  }, [read]);

  /**
   * A file written anywhere under the root changes the answer.
   *
   * A store subscription rather than an effect over `fsRevision`: the read has
   * to happen when a batch lands, and the sections a person has opened must
   * survive it. `git status` on a large repository is tens of milliseconds and
   * the watcher already batches.
   */
  useEffect(
    () =>
      useExplorer.subscribe((state, previous) => {
        if (state.fsRevision !== previous.fsRevision) {
          void read(false);
        }
      }),
    [read],
  );

  const refresh = useCallback(() => {
    setLoading(true);
    void read(false);
  }, [read]);

  const scrollTo = (path: string) => {
    setOpen((current) => new Set(current).add(path));
    // After the section is opened, so the scroll lands on its full height.
    window.requestAnimationFrame(() => {
      sections.current.get(path)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  if (loading && !status) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
        <Spinner className="size-3.5" />
        Reading the working tree…
      </div>
    );
  }

  if (!status?.isRepository) {
    return (
      <EmptyState
        description={`${project.name} is not a git repository, so there is nothing to review.`}
        icon={GitCompare}
        title="Not a repository"
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-9 shrink-0 items-center gap-2 border-b px-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button className="h-6 gap-1 px-2 text-[13px] font-medium" size="sm" variant="ghost">
              {SCOPE_LABELS[scope]}
              <ChevronDown className="size-3 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-52">
            <DropdownMenuLabel className="text-xs">Compare against</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {(Object.keys(SCOPE_LABELS) as ReviewTabModel["scope"][]).map((option) => (
              <DropdownMenuCheckboxItem
                checked={option === scope}
                key={option}
                onSelect={() => update(tabId, { scope: option })}
              >
                {SCOPE_LABELS[option]}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Totals deletions={status.deletions} insertions={status.insertions} />

        <div className="flex-1" />

        {status.branch ? (
          <span className="truncate text-[12px] text-muted-foreground">{status.branch}</span>
        ) : null}

        <Button
          aria-label="Refresh"
          className="size-6 text-muted-foreground"
          onClick={refresh}
          size="icon-xs"
          variant="ghost"
        >
          <RotateCw className={cn("size-3.5", loading && "animate-spin")} />
        </Button>

        <CommitPopover
          disabled={status.files.length === 0}
          onDone={refresh}
          projectId={project.id}
        />
      </header>

      {status.files.length === 0 ? (
        <EmptyState
          description={
            scope === "all"
              ? "The working tree matches HEAD. Diffs from an agent's turn will land here."
              : "Nothing changed in that window."
          }
          icon={GitCompare}
          title="No changes"
        />
      ) : (
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1 overflow-auto" ref={scrollRef}>
            {status.files.map((file) => (
              <FileSection
                file={file}
                key={file.path}
                onToggle={() =>
                  setOpen((current) => {
                    const next = new Set(current);
                    if (!next.delete(file.path)) {
                      next.add(file.path);
                    }
                    return next;
                  })
                }
                open={open.has(file.path)}
                projectId={project.id}
                ref={(node) => {
                  if (node) {
                    sections.current.set(file.path, node);
                  } else {
                    sections.current.delete(file.path);
                  }
                }}
                scope={scope}
              />
            ))}
          </div>

          <aside className="w-56 shrink-0 overflow-auto border-l bg-sidebar/40">
            <p className="px-3 pt-3 pb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              {status.files.length} file{status.files.length === 1 ? "" : "s"}
            </p>
            {status.files.map((file) => (
              <RailRow file={file} key={file.path} onSelect={() => scrollTo(file.path)} />
            ))}
          </aside>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Pieces                                                                      */
/* -------------------------------------------------------------------------- */

function Totals({ insertions, deletions }: { insertions: number; deletions: number }) {
  return (
    <span className="flex shrink-0 items-center gap-1.5 font-mono text-[12px]">
      <span className="text-emerald-600 dark:text-emerald-400">+{insertions}</span>
      <span className="text-rose-600 dark:text-rose-400">−{deletions}</span>
    </span>
  );
}

function RailRow({ file, onSelect }: { file: ChangedFile; onSelect: () => void }) {
  const badge = STATUS_BADGES[file.status];
  const name = file.path.split("/").pop() ?? file.path;
  return (
    <button
      className="flex h-7 w-full items-center gap-1.5 px-3 text-left text-[12px] transition-colors hover:bg-accent/50"
      onClick={onSelect}
      title={file.path}
      type="button"
    >
      <span className={cn("w-2 shrink-0 font-mono font-semibold", badge.className)}>
        {badge.letter}
      </span>
      <FileIcon className="size-3 shrink-0 text-muted-foreground" path={file.path} />
      <span className="min-w-0 flex-1 truncate">{name}</span>
      <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
        <span className="text-emerald-600 dark:text-emerald-400">+{file.insertions}</span>{" "}
        <span className="text-rose-600 dark:text-rose-400">−{file.deletions}</span>
      </span>
    </button>
  );
}

function FileSection({
  file,
  projectId,
  scope,
  open,
  onToggle,
  ref,
}: {
  file: ChangedFile;
  projectId: string;
  scope: ReviewTabModel["scope"];
  open: boolean;
  onToggle: () => void;
  ref: (node: HTMLElement | null) => void;
}) {
  const [diff, setDiff] = useState<FileDiff | null>(null);
  const theme = useResolvedTheme();
  setupMonaco();

  useEffect(() => {
    if (!open || diff) {
      return;
    }
    let cancelled = false;
    void window.hardcore.git
      .fileDiff({ projectId, path: file.path, scope: scopeFor(scope) })
      .then((result) => {
        if (!cancelled) {
          setDiff(result);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open, diff, projectId, file.path, scope]);

  const badge = STATUS_BADGES[file.status];
  const lines = useMemo(() => countLines(diff), [diff]);

  return (
    <section className="border-b" ref={ref}>
      <button
        className="flex w-full items-center gap-2 bg-card/60 px-3 py-2 text-left transition-colors hover:bg-accent/40"
        onClick={onToggle}
        type="button"
      >
        {open ? (
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className={cn("shrink-0 font-mono text-[11px] font-semibold", badge.className)}>
          {badge.letter}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12px]" title={file.path}>
          {file.oldPath ? (
            <>
              <span className="text-muted-foreground line-through">{file.oldPath}</span>
              <span className="text-muted-foreground"> → </span>
            </>
          ) : null}
          {file.path}
        </span>
        <Totals deletions={file.deletions} insertions={file.insertions} />
      </button>

      {open ? (
        file.binary ? (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">
            Binary file — no textual diff.
          </p>
        ) : diff ? (
          <div style={{ height: Math.min(560, Math.max(120, lines * 20 + 24)) }}>
            <DiffEditor
              language={languageFor(file.path)}
              modified={diff.after ?? ""}
              options={{
                ...SHARED_EDITOR_OPTIONS,
                // Codex's review is a unified diff, and a pane this wide has
                // no room for two columns.
                renderSideBySide: false,
                readOnly: true,
                renderOverviewRuler: false,
                scrollBeyondLastLine: false,
                hideUnchangedRegions: { enabled: true, revealLineCount: 3, minimumLineCount: 3 },
                scrollbar: { alwaysConsumeMouseWheel: false, verticalScrollbarSize: 10 },
              }}
              original={diff.before ?? ""}
              theme={monacoTheme(theme)}
            />
          </div>
        ) : (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
            <Spinner className="size-3.5" />
            Reading the diff…
          </div>
        )
      ) : null}
    </section>
  );
}

function CommitPopover({
  projectId,
  disabled,
  onDone,
}: {
  projectId: string;
  disabled: boolean;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (push: boolean) => {
    if (message.trim() === "" || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await window.hardcore.git.commit({ projectId, message: message.trim(), push });
      setMessage("");
      setOpen(false);
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <Button className="h-6 gap-1.5 px-2 text-[12px]" disabled={disabled} size="sm" variant="secondary">
          <GitCommitHorizontal className="size-3.5" />
          Commit or push
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-3">
        <p className="mb-2 text-[12px] font-medium">Commit every change</p>
        <Textarea
          autoFocus
          className="min-h-20 text-[13px]"
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Message"
          value={message}
        />
        {error ? <p className="mt-2 text-[11px] text-destructive">{error}</p> : null}
        <div className="mt-2.5 flex items-center justify-end gap-1.5">
          <Button
            className="h-7 text-xs"
            disabled={busy || message.trim() === ""}
            onClick={() => void run(false)}
            size="sm"
            variant="secondary"
          >
            Commit
          </Button>
          <Button
            className="h-7 text-xs"
            disabled={busy || message.trim() === ""}
            onClick={() => void run(true)}
            size="sm"
          >
            {busy ? <Spinner className="size-3" /> : null}
            Commit and push
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * The tab's scope enum as the IPC's `DiffScope`. Mirrors `scopeFor` in
 * `src/main/ipc/explorer.ts`; the strings are git's own `--before=` syntax.
 */
function scopeFor(scope: ReviewTabModel["scope"]) {
  switch (scope) {
    case "all":
      return { kind: "working-tree" } as const;
    case "1h":
      return { kind: "since", since: "1 hour ago" } as const;
    case "4h":
      return { kind: "since", since: "4 hours ago" } as const;
    case "24h":
      return { kind: "since", since: "24 hours ago" } as const;
    case "7d":
      return { kind: "since", since: "7 days ago" } as const;
  }
}

/** How tall a diff needs to be. Monaco has no intrinsic height. */
function countLines(diff: FileDiff | null): number {
  if (!diff) {
    return 6;
  }
  const before = diff.before?.split("\n").length ?? 0;
  const after = diff.after?.split("\n").length ?? 0;
  return Math.max(before, after, 6);
}

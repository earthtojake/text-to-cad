import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  GitCommitHorizontal,
  GitCompare,
  GitPullRequest,
  RotateCw,
} from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type RefObject } from "react";
import { createPromptContext, textPart } from "@text-to-cad/core/prompt";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@renderer/components/ui/alert";
import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { Spinner } from "@renderer/components/ui/spinner";
import { Textarea } from "@renderer/components/ui/textarea";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { useProjectGitInfo } from "@renderer/lib/git-mode";
import { cn } from "@renderer/lib/utils";
import { createDesktopPromptContext } from "./host/promptContext";
import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import {
  REVIEW_SCOPE_LABELS,
  ReviewScopeSchema,
  diffScopeFor,
  scopeNeedsSession,
  type ReviewScope,
  type Session,
} from "@shared/types";
import { errorMessage } from "@shared/ipc/errors";
import type { Project } from "@shared/types";

import { EmptyState } from "@text-to-cad/ui/navigation";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { FileIcon } from "@text-to-cad/ui/navigation";
import { setupMonaco } from "@renderer/features/explorer/renderers/code/editor";
import { ReviewDiff, type ReviewSelection } from "./review-diff";
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
 *
 * ## Scope, and which directory it is taken in
 *
 * `Last turn` and `This session` are measured from revisions main recorded
 * when the turn began and when the session was created — the renderer sends
 * the *name* of the scope and main resolves it, because the marks are its
 * record, not a number the UI is allowed to compute (plan §13, P7).
 *
 * The tab belongs to the session it was opened in (`sessionId`, fixed for
 * the tab's life), and every scope is read for that session: its marks, and
 * its working directory, which for a thread in `worktree` mode is not the
 * project's checkout at all. Choosing a scope changes only the scope.
 *
 * ## Staying current
 *
 * File changes the explorer reports re-read the status in batches: the first
 * at once, then at most one per `STATUS_GAP_MS` (500 ms), the last batch
 * always answered. Only a file the answer says something new about re-reads
 * its diff. A refresh that fails with nothing on screen is an empty state with
 * Try again; one that fails over an earlier answer keeps that answer, under a
 * `role="alert"` strip — "Could not refresh" and Try again. A diff that cannot
 * be read says so with its error and a Retry, over whatever diff it last drew.
 * Each drawn block carries `data-review-ready` once its editor has drawn
 * (`review-diff.tsx`), which is what a reader or a test waits on.
 */

const SCOPES = ReviewScopeSchema.options;

const STATUS_BADGES: Record<ChangedFile["status"], { letter: string; className: string }> = {
  added: { letter: "A", className: "text-emerald-600 dark:text-emerald-400" },
  untracked: { letter: "A", className: "text-emerald-600 dark:text-emerald-400" },
  modified: { letter: "M", className: "text-amber-600 dark:text-amber-400" },
  renamed: { letter: "R", className: "text-sky-600 dark:text-sky-400" },
  deleted: { letter: "D", className: "text-rose-600 dark:text-rose-400" },
};

const FALLBACK_BADGE = { letter: "M", className: "text-amber-600 dark:text-amber-400" };

const badgeFor = (status: ChangedFile["status"]) => STATUS_BADGES[status] ?? FALLBACK_BADGE;

/**
 * The scope is the review's identity: changing it changes every answer on the
 * page — the totals, the file list, each file's two sides. So it is a `key`
 * rather than a dependency, and the body below starts each scope from its own
 * initial state instead of clearing four pieces of the previous one.
 */
export function ReviewTab(props: {
  tabId: string;
  project: Project;
  scope: ReviewScope;
  sessionId: string;
}) {
  return (
    <ReviewBody
      key={`${props.project.id}:${props.scope}:${props.sessionId}`}
      {...props}
    />
  );
}

function ReviewBody({
  tabId,
  project,
  scope,
  sessionId,
}: {
  tabId: string;
  project: Project;
  scope: ReviewScope;
  sessionId: string;
}) {
  const update = useExplorer((state) => state.update);
  const sessions = useSessions((state) => state.sessions);
  const info = useProjectGitInfo(project.id);

  // Review revisions always belong to this tab's immutable session owner.
  const session = sessions.find(row => row.id === sessionId) ?? null;
  const request = useMemo(
    () => ({ projectId: project.id, sessionId }),
    [project.id, sessionId],
  );

  const [status, setStatus] = useState<GitStatus | null>(null);
  // Per file, the answer its diff has to be at least as new as. A file's
  // stamp moves only when that answer says something new about it — its
  // entry changed, the watcher saw it written, Refresh or a new scope asked
  // for everything — so an agent writing one file does not re-read the diff
  // of every open section (`fileStamps`).
  const [stamps, setStamps] = useState<ReadonlyMap<string, number>>(() => new Map());
  const answers = useRef(0);
  const entries = useRef(new Map<string, string>());
  const written = useRef(new Set<string>());
  const everything = useRef(true);
  // Status reads while writes stream: the first at once, then at most one
  // per STATUS_GAP_MS, the last batch always answered.
  const lastBatchRead = useRef(Number.NEGATIVE_INFINITY);
  const trailingRead = useRef<number | null>(null);
  // A read that failed: git's own words, shown with a retry. Not the same as
  // `isRepository: false`, which is an answer — this is the absence of one.
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [committing, setCommitting] = useState(false);
  const commitTrigger = useRef<HTMLButtonElement | null>(null);
  // Per mounted tab: two Review tabs must not share the id aria-controls names.
  const commitPanelId = useId();
  const closeCommit = useCallback(() => {
    setCommitting(false);
    commitTrigger.current?.focus();
  }, []);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sections = useRef(new Map<string, HTMLElement>());
  // Reads overlap — the first one, a refresh, every batch of file changes —
  // and answer in any order. Only the latest one asked is allowed to land, so
  // an older, slower answer cannot replace a newer one.
  const latestRead = useRef(0);
  const stampsRef = useRef<ReadonlyMap<string, number>>(new Map());
  // Opening the top files is owed by the first read even when a later read
  // supersedes it; the read that lands pays it.
  const owesOpenTop = useRef(false);

  const read = useCallback(
    (openTop: boolean) => {
      const sequence = ++latestRead.current;
      if (openTop) {
        owesOpenTop.current = true;
        everything.current = true;
      }
      // One read per refresh, whatever the scope: the answer carries the
      // working tree's file count for the commit button (`workingFiles`).
      return window.textToCad.git.status({ ...request, scope: diffScopeFor(scope) }).then(
        (next) => {
          if (sequence !== latestRead.current) return;
          setStatus(next);
          answers.current += 1;
          const nextStamps = fileStamps(next.files, {
            answer: answers.current,
            entries: entries.current,
            stamps: stampsRef.current,
            // The watcher's paths are the project's (or worktree's); git's are the repository's.
            written: new Set([...written.current].map((path) => `${next.prefix ?? ""}${path}`)),
            everything: everything.current,
          });
          everything.current = false;
          written.current = new Set();
          stampsRef.current = nextStamps;
          setStamps(nextStamps);
          setError(null);
          setLoading(false);
          if (owesOpenTop.current) {
            owesOpenTop.current = false;
            // The first few files open by default: a review whose sections are
            // all shut is a list of filenames, which is not a review. Binary
            // files are skipped — they have no diff to show, and a review that
            // opens on three "Binary file" panels has told you nothing.
            setOpen(
              new Set(
                next.files
                  .filter((file) => !file.binary)
                  .slice(0, 3)
                  .map((file) => file.path),
              ),
            );
          }
        },
        (failure: unknown) => {
          if (sequence !== latestRead.current) return;
          setError(errorMessage(failure));
          setLoading(false);
        },
      );
    },
    [request, scope],
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
  useEffect(() => {
    const unsubscribe = useExplorer.subscribe((state, previous) => {
      if (state.fsRevision === previous.fsRevision) return;
      for (const change of state.changedEntries) {
        written.current.add(change.path);
        if (change.kind === "moved") written.current.add(change.previousPath);
      }
      if (trailingRead.current !== null) return;
      const go = () => {
        trailingRead.current = null;
        lastBatchRead.current = Date.now();
        void read(false);
      };
      const wait = lastBatchRead.current + STATUS_GAP_MS - Date.now();
      if (wait <= 0) go();
      else trailingRead.current = window.setTimeout(go, wait);
    });
    return () => {
      unsubscribe();
      if (trailingRead.current !== null) window.clearTimeout(trailingRead.current);
      trailingRead.current = null;
    };
  }, [read]);

  const refresh = useCallback(() => {
    setLoading(true);
    everything.current = true;
    void read(false);
  }, [read]);

  const chooseScope = (next: ReviewScope) => {
    update(tabId, { scope: next });
  };

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

  if (error && !status) {
    return (
      <EmptyState
        action={<Button className="h-7 text-[12px]" onClick={refresh} size="sm" variant="outline">Try again</Button>}
        description={error}
        icon={AlertTriangle}
        title="Could not read the changes"
        tone="warn"
      />
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

  // Commits a Push would send: none when there is nowhere to push them (an
  // upstream that is a local branch counts them as ahead all the same).
  const pushable = info?.hasRemote ? status.ahead : 0;
  const commitOpen = committing && (status.workingFiles > 0 || pushable > 0);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-9 shrink-0 items-center gap-2 border-b px-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button className="h-6 gap-1 px-2 text-[13px] font-medium" size="sm" variant="ghost">
              {REVIEW_SCOPE_LABELS[scope]}
              <ChevronDown className="size-3 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel className="text-xs">Compare against</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {SCOPES.map((option) => (
              <DropdownMenuCheckboxItem
                checked={option === scope}
                // The two session scopes need a thread to measure from; with
                // none they are shown and disabled rather than hidden, so the
                // menu does not change shape depending on what is selected.
                disabled={scopeNeedsSession(option) && !session}
                key={option}
                onSelect={() => chooseScope(option)}
              >
                {REVIEW_SCOPE_LABELS[option]}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {status.unmarked ? null : <Totals deletions={status.deletions} insertions={status.insertions} />}

        <div className="flex-1" />

        {/*
          The branch alone: it says where a commit from this header would
          land. The thread's title is the session header's, one pane over;
          repeated here it only ever showed truncated. Its directory — a
          worktree's is not the project's — is the hover.
        */}
        {status.branch ? (
          <TooltipHint content={session?.cwd}>
            <span className="min-w-0 truncate text-[12px] text-muted-foreground">
              {status.branch}
            </span>
          </TooltipHint>
        ) : null}

        {/* Always mounted, so the words arriving in it are announced; the spinner is only drawn. */}
        <span aria-live="polite" className="sr-only" role="status">
          {loading ? "Refreshing…" : ""}
        </span>
        <Button
          aria-busy={loading}
          aria-label="Refresh"
          className="size-6 text-muted-foreground"
          onClick={refresh}
          size="icon-xs"
          variant="ghost"
        >
          <RotateCw className={cn("size-3.5", loading && "animate-spin")} />
        </Button>

        <CommitTrigger
          canPush={Boolean(info?.hasRemote)}
          // The panel commits the whole working tree (`git add -A`),
          // whatever scope is on screen, so its button follows the working
          // tree: a "Last turn" with nothing in it can sit beside uncommitted
          // work from earlier, and a scope full of committed history beside a
          // clean tree.
          fileCount={status.workingFiles}
          // A push that failed after its commit leaves a clean tree and
          // commits the remote lacks: the same button sends them.
          ahead={pushable}
          onToggle={() => setCommitting((current) => !current)}
          panelId={commitPanelId}
          open={commitOpen}
          ref={commitTrigger}
        />
      </header>

      {commitOpen ? (
        <CommitPanel
          ahead={pushable}
          canOpenPullRequest={Boolean(info?.hasGh && info.hasRemote)}
          canPush={Boolean(info?.hasRemote)}
          fileCount={status.workingFiles}
          id={commitPanelId}
          onClose={closeCommit}
          onDone={refresh}
          request={request}
          session={session}
        />
      ) : null}

      {/* A re-read that failed keeps the last answer on screen, marked stale. */}
      {error ? (
        <div className="flex shrink-0 items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-[12px]" role="alert">
          <AlertTriangle className="size-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <TooltipHint content={error} overflowOnly>
            <span className="min-w-0 flex-1 truncate">Could not refresh: {error}</span>
          </TooltipHint>
          <Button className="h-6 px-2 text-[12px]" onClick={refresh} size="sm" variant="outline">Try again</Button>
        </div>
      ) : null}

      {/*
        No commits yet, so no mark could be taken: the scope is the working
        tree, and it says so rather than passing it off as the turn's diff.
      */}
      {status.fromStart ? (
        <p className="shrink-0 border-b px-3 py-1.5 text-[12px] text-muted-foreground">
          {fromStartNote(scope)}
        </p>
      ) : null}

      {/*
        Main had no recorded revision for this scope. Its answer is empty on
        purpose — the working tree would be a different revision under this
        scope's name — so say why rather than "No changes".
      */}
      {status.unmarked ? (
        <EmptyState
          description={unmarkedDescription(status.unmarked)}
          icon={GitCompare}
          title={status.unmarked === "turn" ? "No turn recorded yet" : "No session start recorded"}
        />
      ) : status.files.length === 0 ? (
        <EmptyState
          description={emptyDescription(scope)}
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
                ref={(node) => {
                  if (node) {
                    sections.current.set(file.path, node);
                  } else {
                    sections.current.delete(file.path);
                  }
                }}
                request={request}
                revision={stamps.get(file.path) ?? 0}
                root={session?.cwd ?? null}
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

/** The shortest gap between two status reads that batches of file changes ask for. */
const STATUS_GAP_MS = 500;

/**
 * Each file's stamp for a new status answer: the answer's own number when
 * something about the file is new — its entry (status, counts, old path)
 * differs from the last answer's, the watcher reported it written since, or
 * everything is asked for — and the stamp it had otherwise. `entries` is
 * updated in place to this answer's.
 */
function fileStamps(
  files: readonly ChangedFile[],
  at: {
    answer: number;
    entries: Map<string, string>;
    stamps: ReadonlyMap<string, number>;
    written: ReadonlySet<string>;
    everything: boolean;
  },
): ReadonlyMap<string, number> {
  const next = new Map<string, number>();
  const seen = new Map<string, string>();
  for (const file of files) {
    const entry = JSON.stringify([file.status, file.insertions, file.deletions, file.oldPath ?? null, file.binary]);
    seen.set(file.path, entry);
    const previous = at.stamps.get(file.path);
    const fresh = at.everything || previous === undefined || at.entries.get(file.path) !== entry
      || at.written.has(file.path) || (file.oldPath !== undefined && at.written.has(file.oldPath));
    next.set(file.path, fresh ? at.answer : previous);
  }
  at.entries.clear();
  for (const [path, entry] of seen) at.entries.set(path, entry);
  return next;
}

// A repository with no commits never lands here: main answers that case from
// the working tree (`fromStart`).
// Each sentence is written for its scope rather than built around the menu's label: a label is a
// name, and "so This session is measured…" reads as one pasted into the middle of a sentence.
function unmarkedDescription(which: "turn" | "session"): string {
  return which === "turn"
    ? "A turn is measured from the prompt that starts it, so there is nothing to show until the next one. The working tree's changes are under “All changes”."
    : "No revision was recorded when this session began, so there is nothing to measure it from. The working tree's changes are under “All changes”.";
}

/** What `fromStartNote` says is measured; the time windows are "this window". */
const FROM_START_SUBJECT: Partial<Record<ReviewScope, string>> = {
  turn: "the last turn",
  session: "this session",
  all: "every change",
};

function fromStartNote(scope: ReviewScope): string {
  return `This repository has no commits yet, so ${FROM_START_SUBJECT[scope] ?? "this window"} is measured from the repository's start.`;
}

function emptyDescription(scope: ReviewScope): string {
  switch (scope) {
    case "all":
      return "The working tree matches HEAD. Diffs from an agent's turn will land here.";
    case "turn":
      return "Nothing changed in the newest turn.";
    case "session":
      return "Nothing has changed since this session started.";
    default:
      return "Nothing changed in that window.";
  }
}

/* -------------------------------------------------------------------------- */
/* Pieces                                                                      */
/* -------------------------------------------------------------------------- */

/** The project and the session every read in this tab is answered for. */
type ReviewRequest = { projectId: string; sessionId: string };

function Totals({ insertions, deletions }: { insertions: number; deletions: number }) {
  return (
    <span className="flex shrink-0 items-center gap-1.5 font-mono text-[12px]">
      <span className="text-emerald-600 dark:text-emerald-400">+{insertions}</span>
      <span className="text-rose-600 dark:text-rose-400">−{deletions}</span>
    </span>
  );
}

function RailRow({ file, onSelect }: { file: ChangedFile; onSelect: () => void }) {
  const badge = badgeFor(file.status);
  const name = file.path.split("/").pop() ?? file.path;
  return (
    <TooltipHint content={file.path}>
      <button
        className="flex h-7 w-full items-center gap-1.5 px-3 text-left text-[13px] transition-colors hover:bg-accent/50"
        onClick={onSelect}
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
    </TooltipHint>
  );
}

function FileSection({
  root,
  file,
  request,
  scope,
  revision,
  open,
  onToggle,
  ref,
}: {
  root: string | null;
  file: ChangedFile;
  request: ReviewRequest;
  scope: ReviewScope;
  /** The status answer this file's diff must be read for: a newer one re-reads it when open. */
  revision: number;
  open: boolean;
  onToggle: () => void;
  ref: (node: HTMLElement | null) => void;
}) {
  // The diff and the status answer it was read for. A diff from an older
  // answer stays on screen while the newer one is read, rather than
  // flickering back to a spinner on every batch of file changes.
  const [loaded, setLoaded] = useState<{ diff: FileDiff; revision: number } | null>(null);
  const diff = loaded?.diff ?? null;
  const current = loaded?.revision === revision;
  // A read that failed says so, over whatever diff is still on screen, until
  // a read succeeds: swallowed, it left "Reading the diff…" up for good.
  // `attempt` is Retry's: the same revision, read again.
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const selection = useRef<ReviewSelection | null>(null);
  const promptContext = useMemo(() => createDesktopPromptContext(request.projectId, root, JSON.stringify(["desktop", request.projectId, root]), request.sessionId), [request.projectId, root, request.sessionId]);
  const requestRevision = () => {
    const selected = selection.current;
    const excerpt = selected ? `\nSelected ${selected.side} lines ${selected.start}–${selected.end}:\n\`\`\`\n${selected.text}\n\`\`\`\n` : "";
    void promptContext.deliver(createPromptContext([textPart(`Please revise ${file.path} (${REVIEW_SCOPE_LABELS[scope]}).\n${excerpt}Requested change: `)])).then(result => {
      if (result.status === "failed" || result.status === "cancelled") toast.error(result.message ?? "Context could not be added to the draft.");
    });
  };
  const theme = useResolvedTheme();
  setupMonaco();

  // One read at a time, and it is never cancelled by a newer stamp: a file
  // written faster than its diff can be read (every status answer moves the
  // stamp) would otherwise cancel every read and show "Reading the diff…"
  // for as long as the writes go on. The read that lands is shown, and the
  // stamp it is behind asks for the next (`landed`).
  const reading = useRef(false);
  const mounted = useRef(true);
  const [landed, setLanded] = useState(0);
  // The newest stamp, for a read that settles after it moved: the stamp's own
  // re-run found a read in flight and asked nothing.
  const latest = useRef(revision);
  useEffect(() => {
    latest.current = revision;
  }, [revision]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!open || current || reading.current) {
      return;
    }
    reading.current = true;
    const asked = revision;
    void window.textToCad.git
      .fileDiff({ ...request, path: file.path, scope: diffScopeFor(scope) })
      .then((result) => {
        reading.current = false;
        if (!mounted.current) return;
        setLoaded({ diff: result, revision: asked });
        setFailure(null);
        setLanded((count) => count + 1);
      })
      .catch((error: unknown) => {
        reading.current = false;
        if (!mounted.current) return;
        // The failure is shown with its Retry. A stamp that moved while it
        // was read asks again, as a landed read would; the same stamp waits
        // for Retry or a newer one.
        setFailure(errorMessage(error));
        if (latest.current !== asked) setLanded((count) => count + 1);
      });
  }, [open, current, request, file.path, scope, revision, attempt, landed]);
  const retry = () => {
    setFailure(null);
    setAttempt((count) => count + 1);
  };

  const badge = badgeFor(file.status);

  return (
    <section className="border-b" data-review-file={file.path} ref={ref}>
      {/*
        One row: the toggle takes the name and the counts, and Request
        revision sits after them at the right — a sibling, since a button
        cannot hold a button.
      */}
      <div className="flex min-w-0 items-center gap-1 bg-card/60 pr-2">
        <button
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 pl-3 text-left transition-colors hover:bg-accent/40"
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
          <TooltipHint content={file.path} overflowOnly>
            <span className="min-w-0 flex-1 truncate font-mono text-[12px]">
              {file.oldPath ? (
                <>
                  <span className="text-muted-foreground line-through">{file.oldPath}</span>
                  <span className="text-muted-foreground"> → </span>
                </>
              ) : null}
              {file.path}
            </span>
          </TooltipHint>
          <Totals deletions={file.deletions} insertions={file.insertions} />
        </button>
        <Button
          aria-label={`Request revision for ${file.path}`}
          className="h-6 shrink-0 px-2 text-xs text-muted-foreground hover:text-foreground"
          onClick={requestRevision}
          // Keeps the editor's selection, which is what the request quotes.
          onMouseDown={(event) => event.preventDefault()}
          size="sm"
          variant="ghost"
        >
          Request revision
        </Button>
      </div>

      {open ? (
        file.binary ? (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">
            Binary file — no textual diff.
          </p>
        ) : failure || diff ? (
          <>
            {failure ? (
              <Alert className="m-2 w-auto px-3 py-2 text-xs" variant="destructive">
                <AlertCircle />
                <AlertDescription className="flex min-w-0 flex-row items-center gap-2 text-xs">
                  <span className="min-w-0 flex-1 break-words">Could not read the diff: {failure}</span>
                  <Button className="h-6 shrink-0 px-2 text-[12px]" onClick={retry} size="sm" variant="outline">
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}
            {diff ? (
              <ReviewDiff
                diff={diff}
                onSelect={(next) => {
                  selection.current = next;
                }}
                path={file.path}
                theme={theme}
              />
            ) : null}
          </>
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

/**
 * The header's commit button: `Commit or push` with a remote to push to,
 * plain `Commit` without one — a label that offers a push the panel cannot do
 * is a promise it breaks. Primary, because it is the header's one action —
 * until the panel is open: then the panel's own Commit is the action, and this
 * one is the toggle that opened it, drawn as a pressed outline so the header
 * and the panel do not show two filled Commit buttons one above the other.
 */
function CommitTrigger({
  ahead,
  canPush,
  fileCount,
  open,
  onToggle,
  panelId,
  ref,
}: {
  /** Commits the remote lacks. */
  ahead: number;
  canPush: boolean;
  fileCount: number;
  open: boolean;
  onToggle: () => void;
  /** The panel's id, for aria-controls. */
  panelId: string;
  ref: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <Button
      aria-controls={panelId}
      aria-expanded={open}
      className="h-6 gap-1.5 px-2 text-[12px]"
      disabled={fileCount === 0 && ahead === 0}
      onClick={onToggle}
      ref={ref}
      size="sm"
      variant={open ? "outline" : "default"}
    >
      <GitCommitHorizontal className="size-3.5" />
      {fileCount === 0 && ahead > 0 ? "Push" : canPush ? "Commit or push" : "Commit"}
    </Button>
  );
}

/**
 * The commit form, and `Create pull request` beside it (plan §9).
 *
 * A strip under the header rather than a floating popover: a popover wide
 * enough for a commit message hangs over the first file's header — its name,
 * its `+/−`, its Request revision — and this pushes the files down instead.
 * Escape closes it and gives focus back to the header's button.
 *
 * The settings' commit instructions are the message box's **placeholder**, not
 * text prepended to what the person writes: they are house style for whoever
 * is composing the message, and a GUI that silently pasted them into every
 * commit would be writing commit messages nobody read.
 *
 * The pull-request action is offered only when `gh` is on the PATH and the
 * repository has a remote. Everything else it needs — pushing a branch that
 * has no upstream, choosing the base, the draft setting — main does.
 */
function CommitPanel({
  ahead,
  request,
  session,
  fileCount,
  canOpenPullRequest,
  canPush,
  id,
  onClose,
  onDone,
}: {
  /** Commits the remote lacks: with a clean tree, the panel's one job is to push them. */
  ahead: number;
  request: ReviewRequest;
  session: Session | null;
  /** Files in the working tree — what `Commit` takes, not what the scope shows. */
  fileCount: number;
  canOpenPullRequest: boolean;
  /** A remote to push to; without one `Commit and push` is not offered. */
  canPush: boolean;
  id: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const settings = useSettings((state) => state.settings);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (work: () => Promise<unknown>) => {
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await work();
      setMessage("");
      onClose();
      onDone();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const commit = (push: boolean) => {
    if (message.trim() === "" && fileCount > 0) {
      return;
    }
    void run(async () => {
      const { sha, pushedOnly, pushed } = await window.textToCad.git.commit({ ...request, message: message.trim(), push });
      // The files this message was for were committed by someone else between
      // the last read and this request: say nothing was committed.
      if (pushedOnly && fileCount > 0) {
        toast.success(`Nothing new to commit; pushed ${pushed ?? 0} ${pushed === 1 ? "commit" : "commits"}`);
        return;
      }
      toast.success(
        fileCount === 0 ? `Pushed ${sha.slice(0, 7)}` : `${push ? "Committed and pushed" : "Committed"} ${sha.slice(0, 7)}`,
      );
    });
  };

  /**
   * The pull request's title is the message's first line, and its body the
   * rest — git's own convention, so one box does for both and there is no
   * second form to fill in. A session with a title uses that instead when the
   * box is empty: the thread already named itself from the first prompt.
   */
  const pullRequest = () => {
    const [first, ...rest] = message.trim().split("\n");
    const title = first?.trim() || session?.title || "";
    if (!title) {
      return;
    }
    void run(async () => {
      const { url } = await window.textToCad.git.pullRequest({
        ...request,
        title,
        body: rest.join("\n").trim(),
      });
      await window.textToCad.shell.openExternal({ url });
    });
  };

  return (
    <section
      aria-label="Commit changes"
      className="shrink-0 border-b bg-card/60 px-3 py-2.5"
      id={id}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <p className="mb-2 text-[12px] font-medium">
        {fileCount === 0
          ? `${ahead} ${ahead === 1 ? "commit" : "commits"} not pushed`
          : `Commit ${fileCount} ${fileCount === 1 ? "file" : "files"}`}
      </p>
      {/* Pushing commits already made needs no message; the box stays only as a pull request's title. */}
      {fileCount > 0 || canOpenPullRequest ? (
        <>
        <Textarea
          aria-label="Commit message"
          autoFocus
          className="min-h-16 text-[13px]"
          onChange={(event) => setMessage(event.target.value)}
          placeholder={settings?.commitInstructions?.trim() || "Message"}
          value={message}
        />
        {settings?.commitInstructions?.trim() ? (
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            {settings.commitInstructions.trim()}
          </p>
        ) : null}
        </>
      ) : null}
      {error ? <p className="mt-2 text-[11px] text-destructive">{error}</p> : null}
      <div className="mt-2.5 flex items-center gap-1.5">
        {canOpenPullRequest ? (
          <Button
            className="h-7 gap-1.5 text-xs"
            disabled={busy || (message.trim() === "" && !session?.title)}
            onClick={pullRequest}
            size="sm"
            variant="ghost"
          >
            <GitPullRequest className="size-3.5" />
            Create pull request
          </Button>
        ) : null}
        <div className="flex-1" />
        <Button className="h-7 text-xs" onClick={onClose} size="sm" variant="ghost">
          Cancel
        </Button>
        {fileCount === 0 ? (
          <Button className="h-7 text-xs" disabled={busy} onClick={() => commit(true)} size="sm">
            {busy ? <Spinner className="size-3" /> : null}
            Push
          </Button>
        ) : (
          <>
            <Button
              className="h-7 text-xs"
              disabled={busy || message.trim() === ""}
              onClick={() => commit(false)}
              size="sm"
              // With no remote this is the panel's one action, so it takes the fill.
              variant={canPush ? "secondary" : "default"}
            >
              {busy && !canPush ? <Spinner className="size-3" /> : null}
              Commit
            </Button>
            {canPush ? (
              <Button
                className="h-7 text-xs"
                disabled={busy || message.trim() === ""}
                onClick={() => commit(true)}
                size="sm"
              >
                {busy ? <Spinner className="size-3" /> : null}
                Commit and push
              </Button>
            ) : null}
          </>
        )}
      </div>
      {canOpenPullRequest ? (
        <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
          {settings?.pullRequestInstructions?.trim() ||
            "The first line is the title, the rest the description. Uncommitted work is not included."}
        </p>
      ) : null}
    </section>
  );
}


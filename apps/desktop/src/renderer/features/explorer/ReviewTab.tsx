import { DiffEditor } from "@monaco-editor/react";
import {
  ChevronDown,
  ChevronRight,
  GitCommitHorizontal,
  GitCompare,
  GitPullRequest,
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
import { useProjectGitInfo } from "@renderer/lib/git-mode";
import { cn } from "@renderer/lib/utils";
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
 *
 * ## Scope, and which directory it is taken in
 *
 * `Last turn` and `This session` are measured from revisions main recorded
 * when the turn began and when the session was created — the renderer sends
 * the *name* of the scope and main resolves it, because the marks are its
 * record, not a number the UI is allowed to compute (plan §13, P7).
 *
 * Choosing one of them pins the session onto the tab. That matters because the
 * strip belongs to the **project**: a review that followed whichever thread
 * happened to be selected would change what it was showing every time someone
 * clicked another row in the sidebar. A pinned session also moves the whole
 * read into that session's working directory, which for a thread in `worktree`
 * mode is not the project's checkout at all.
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
  sessionId: string | null;
}) {
  return (
    <ReviewBody
      key={`${props.project.id}:${props.scope}:${props.sessionId ?? ""}`}
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
  sessionId: string | null;
}) {
  const update = useExplorer((state) => state.update);
  const sessions = useSessions((state) => state.sessions);
  const activeSessionId = useSessions((state) => state.activeId);
  const info = useProjectGitInfo(project.id);

  // The session the scope is measured in. A pinned one that has since been
  // deleted falls back to the project, which is what an unpinned tab reads.
  const pinned = sessions.find((candidate) => candidate.id === sessionId) ?? null;
  const candidate =
    pinned ?? sessions.find((session) => session.id === activeSessionId) ?? null;
  const target = scopeNeedsSession(scope) ? candidate : pinned;
  const request = useMemo(
    () => ({ projectId: project.id, ...(target ? { sessionId: target.id } : {}) }),
    [project.id, target],
  );

  const [status, setStatus] = useState<GitStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sections = useRef(new Map<string, HTMLElement>());

  const read = useCallback(
    (openTop: boolean) =>
      window.hardcore.git
        .status({ ...request, scope: diffScopeFor(scope) })
        .catch(() => null)
        .then((next) => {
          setStatus(next);
          setLoading(false);
          if (openTop) {
            // The first few files open by default: a review whose sections are
            // all shut is a list of filenames, which is not a review. Binary
            // files are skipped — they have no diff to show, and a review that
            // opens on three "Binary file" panels has told you nothing.
            setOpen(
              new Set(
                (next?.files ?? [])
                  .filter((file) => !file.binary)
                  .slice(0, 3)
                  .map((file) => file.path),
              ),
            );
          }
        }),
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

  const chooseScope = (next: ReviewScope) => {
    // Pin the session the moment a scope needs one, so the tab keeps showing
    // the thread it was opened against rather than following the sidebar.
    update(tabId, {
      scope: next,
      sessionId: scopeNeedsSession(next) ? (candidate?.id ?? null) : null,
    });
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
                disabled={scopeNeedsSession(option) && !candidate}
                key={option}
                onSelect={() => chooseScope(option)}
              >
                {REVIEW_SCOPE_LABELS[option]}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Totals deletions={status.deletions} insertions={status.insertions} />

        <div className="flex-1" />

        {target ? (
          <span
            className="truncate text-[12px] text-muted-foreground"
            title={`${target.title} · ${target.cwd}`}
          >
            {target.title}
          </span>
        ) : null}

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
          canOpenPullRequest={Boolean(info?.hasGh && info.hasRemote)}
          disabled={status.files.length === 0}
          onDone={refresh}
          request={request}
          session={target}
        />
      </header>

      {status.files.length === 0 ? (
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

/** The project (and optionally session) every read in this tab is answered for. */
type ReviewRequest = { projectId: string; sessionId?: string };

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
  request,
  scope,
  open,
  onToggle,
  ref,
}: {
  file: ChangedFile;
  request: ReviewRequest;
  scope: ReviewScope;
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
      .fileDiff({ ...request, path: file.path, scope: diffScopeFor(scope) })
      .then((result) => {
        if (!cancelled) {
          setDiff(result);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open, diff, request, file.path, scope]);

  const badge = badgeFor(file.status);
  const height = useMemo(() => sectionHeight(diff), [diff]);

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
          <div style={{ height }}>
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

/**
 * `Commit or push`, and `Create pull request` beside it (plan §9).
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
function CommitPopover({
  request,
  session,
  disabled,
  canOpenPullRequest,
  onDone,
}: {
  request: ReviewRequest;
  session: Session | null;
  disabled: boolean;
  canOpenPullRequest: boolean;
  onDone: () => void;
}) {
  const settings = useSettings((state) => state.settings);
  const [open, setOpen] = useState(false);
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
      setOpen(false);
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const commit = (push: boolean) => {
    if (message.trim() === "") {
      return;
    }
    void run(() => window.hardcore.git.commit({ ...request, message: message.trim(), push }));
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
      const { url } = await window.hardcore.git.pullRequest({
        ...request,
        title,
        body: rest.join("\n").trim(),
      });
      await window.hardcore.shell.openExternal({ url });
    });
  };

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <Button className="h-6 gap-1.5 px-2 text-[12px]" disabled={disabled} size="sm" variant="secondary">
          <GitCommitHorizontal className="size-3.5" />
          Commit or push
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-3">
        <p className="mb-2 text-[12px] font-medium">Commit every change</p>
        <Textarea
          aria-label="Commit message"
          autoFocus
          className="min-h-20 text-[13px]"
          onChange={(event) => setMessage(event.target.value)}
          placeholder={settings?.commitInstructions?.trim() || "Message"}
          value={message}
        />
        {settings?.commitInstructions?.trim() ? (
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            {settings.commitInstructions.trim()}
          </p>
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
          <Button
            className="h-7 text-xs"
            disabled={busy || message.trim() === ""}
            onClick={() => commit(false)}
            size="sm"
            variant="secondary"
          >
            Commit
          </Button>
          <Button
            className="h-7 text-xs"
            disabled={busy || message.trim() === ""}
            onClick={() => commit(true)}
            size="sm"
          >
            {busy ? <Spinner className="size-3" /> : null}
            Commit and push
          </Button>
        </div>
        {canOpenPullRequest ? (
          <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
            {settings?.pullRequestInstructions?.trim() ||
              "The first line is the title, the rest the description. Uncommitted work is not included."}
          </p>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * How tall a section needs to be. Monaco has no intrinsic height, so someone
 * has to guess.
 *
 * The guess is the *change*, not the file. `hideUnchangedRegions` collapses
 * everything that did not move into a one-line "407 hidden lines" band, so
 * sizing by the file's length leaves a screen of blank editor under a
 * four-line edit — which is what the first review screenshot showed.
 */
const LINE_HEIGHT = 20;

function sectionHeight(diff: FileDiff | null): number {
  if (!diff) {
    return 120;
  }
  // The changed lines, plus the context Monaco keeps around each collapsed
  // band, plus the band itself.
  const lines = diff.insertions + diff.deletions + 8;
  return Math.min(560, Math.max(120, lines * LINE_HEIGHT));
}

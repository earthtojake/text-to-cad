import { useEffect, useId, useRef, useState } from "react";
import {
  Archive,
  ArchiveRestore,
  Circle,
  CircleDot,
  Copy,
  GitBranch,
  GitFork,
  LoaderCircle,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { cn } from "cn";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { Button } from "@renderer/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@renderer/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { MenuItem, MenuKind, MenuSeparator } from "@renderer/features/sidebar/menu";
import { openSessionReview } from "@renderer/features/sidebar/open-review";
import { gitGlyphFor, gitGlyphLabel, useProjectGitInfo } from "@renderer/lib/git-mode";
import { SESSION_GLYPH_LABELS, sessionGlyphFor } from "@renderer/lib/sidebar";
import { useSessions } from "@renderer/state/sessions";
import type { Session, SessionStatus } from "@shared/types";

/**
 * One thread: its state as a leading glyph, the title, and — on hover, or
 * with the menu open — the `…` its actions live behind (the same list the
 * right-click menu draws).
 *
 * Two glyphs, and they answer two different questions. The leading one is
 * the *session's* state, which is what a sidebar is read for: whether a
 * thread is working, has failed, or is waiting on an answer. The trailing one
 * is *git's* (`lib/git-mode.ts`) — a worktree, or a branch that is not the
 * project's own — and it is a fact about where the thread writes. They used
 * to share a slot, so a running worktree thread looked like a running
 * checkout one; now neither hides the other.
 */
export function SessionRow({
  session,
  selected,
  projectName,
  showBranch,
  onSelect,
}: {
  session: Session;
  selected: boolean;
  /** Drawn as a faint suffix where the section is not one project's (Pinned). */
  projectName?: string | undefined;
  /** `Show branch` in the filter menu: the branch, faint, after the title. */
  showBranch: boolean;
  onSelect: () => void;
}) {
  const rename = useSessions((state) => state.rename);
  const archive = useSessions((state) => state.archive);
  const setPinned = useSessions((state) => state.setPinned);
  const remove = useSessions((state) => state.remove);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.title);
  const statusId = useId();
  // Idle is the absence of news; saying it on every quiet row would be noise.
  const statusText = sessionGlyphFor(session.status) === "idle" ? null : SESSION_GLYPH_LABELS[sessionGlyphFor(session.status)];

  // Enter and Escape end the edit by unmounting the box that had focus, which left it on the page;
  // the title button takes it back. A blur that ends the edit (a click elsewhere) must not.
  const titleButton = useRef<HTMLButtonElement | null>(null);
  const refocusTitle = useRef(false);
  useEffect(() => {
    if (!editing && refocusTitle.current) {
      refocusTitle.current = false;
      titleButton.current?.focus();
    }
  }, [editing]);

  // Enter and Escape settle the edit themselves; a blur that follows (some browsers blur an input
  // as it unmounts) must commit nothing: Escape never renames, and Enter must not rename twice.
  const settled = useRef(false);
  const startRename = () => {
    settled.current = false;
    setDraft(session.title);
    setEditing(true);
  };
  // The rename box must not open while the menu that chose it is still closing. Radix's focus scope
  // pulls focus back into a menu that is still trapped (stealing the box's autoFocus) and, a tick
  // after close, restores focus to the `…` trigger; either blurs the box, and the blur commits the
  // draft. So Rename only raises this flag, and the box opens from the menu's own close-focus event,
  // when both are done; that event is not given to the trigger.
  const renameChosen = useRef(false);
  const openRenameAfterMenu = (event: Event) => {
    if (renameChosen.current) {
      renameChosen.current = false;
      event.preventDefault();
      startRename();
    }
  };
  const commitRename = () => {
    if (settled.current) return;
    settled.current = true;
    setEditing(false);
    if (draft.trim() && draft.trim() !== session.title) {
      void rename(session.id, draft);
    }
  };

  const menuItems = (
    <>
      <MenuItem
        icon={session.pinned ? <PinOff /> : <Pin />}
        label={session.pinned ? "Unpin" : "Pin"}
        onSelect={() => void setPinned(session.id, !session.pinned)}
      />
      <MenuItem
        icon={<Pencil />}
        label="Rename"
        onSelect={() => {
          renameChosen.current = true;
        }}
      />
      <MenuItem
        icon={session.archived ? <ArchiveRestore /> : <Archive />}
        label={session.archived ? "Unarchive" : "Archive"}
        onSelect={() => void archive(session.id, !session.archived)}
      />
      <MenuItem
        icon={<Copy />}
        label="Copy path"
        onSelect={() => void navigator.clipboard.writeText(session.cwd)}
      />
      <MenuSeparator />
      <MenuItem
        destructive
        icon={<Trash2 />}
        label="Delete"
        onSelect={() => void remove(session.id)}
      />
    </>
  );

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className={cn(
            "group/session flex h-7 min-w-0 items-center gap-1.5 rounded-md pr-1 pl-2 transition-colors",
            // The keyboard ring is the row's, not the title button's 153×20 box inside it.
            "has-[[data-session-row-title]:focus-visible]:ring-2 has-[[data-session-row-title]:focus-visible]:ring-inset has-[[data-session-row-title]:focus-visible]:ring-ring",
            selected
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "hover:bg-sidebar-accent/60",
          )}
          data-pinned={session.pinned ? "" : undefined}
          data-session-row={session.id}
          data-status={session.status}
        >
          <StateGlyph status={session.status} />
          {statusText ? (
            <span className="sr-only" id={statusId}>
              {statusText}
            </span>
          ) : null}
          {editing ? (
            <input
              aria-label="Session title"
              autoFocus
              className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
              onBlur={commitRename}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  // Not let through: the keypress that follows would land on the title button, which has
                  // the focus by then, and click it straight back into the box.
                  event.preventDefault();
                  refocusTitle.current = true;
                  commitRename();
                } else if (event.key === "Escape") {
                  refocusTitle.current = true;
                  settled.current = true;
                  setEditing(false);
                }
              }}
              value={draft}
            />
          ) : (
            // The whole title, when the row has cut it short.
            <TooltipHint content={projectName ? `${session.title} — ${projectName}` : session.title} overflowOnly>
              <button
                // The session on screen, said as well as tinted.
                aria-current={selected ? "page" : undefined}
                // The state glyph sits before this button and is not a tab stop, so its word rides
                // here: read as the row's description, it is heard from the one place focus lands.
                aria-describedby={statusText ? statusId : undefined}
                className="min-w-0 flex-1 truncate text-left text-[13px] focus-visible:outline-none"
                data-session-row-title
                ref={titleButton}
                onClick={onSelect}
                onDoubleClick={startRename}
                type="button"
              >
                {session.title}
                {showBranch && session.branch ? (
                  <span className="ml-1.5 text-[11px] text-muted-foreground" data-session-branch>
                    {session.branch}
                  </span>
                ) : null}
              </button>
            </TooltipHint>
          )}
          {projectName ? (
            <span
              className="max-w-[40%] shrink-0 truncate text-[11px] text-muted-foreground"
              data-session-project
            >
              {projectName}
            </span>
          ) : null}
          <ChangeCounts
            onOpen={() => {
              onSelect();
              openSessionReview(session.id);
            }}
            session={session}
          />
          <GitGlyph session={session} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label={`${session.title} actions`}
                className="size-5 shrink-0 text-muted-foreground opacity-0 group-hover/session:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
                size="icon-xs"
                variant="ghost"
              >
                <MoreHorizontal className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-40" onCloseAutoFocus={openRenameAfterMenu}>
              <MenuKind.Provider value="dropdown">{menuItems}</MenuKind.Provider>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-40" onCloseAutoFocus={openRenameAfterMenu}>
        <MenuKind.Provider value="context">{menuItems}</MenuKind.Provider>
      </ContextMenuContent>
    </ContextMenu>
  );
}

/**
 * The state, as the one mark on the row that is always drawn: a hollow circle
 * for a thread with nothing to say, a pulsing dot while a turn streams, an
 * accent-coloured ringed dot when the agent is blocked on the person ("needs
 * you" — not a warning; nothing is wrong) and a red triangle when the last
 * turn failed (`lib/sidebar.ts` owns the mapping). Drawn only; the row's title
 * button says the same in words (`aria-describedby`), so the two are not both read.
 */
export function StateGlyph({ status }: { status: SessionStatus }) {
  const glyph = sessionGlyphFor(status);
  // A 16px box the row centres; `leading-none` so the SVG has no line box to
  // sit low in — the glyphs are small, and a pixel off centre shows.
  const box = "flex size-4 shrink-0 items-center justify-center self-center leading-none";
  switch (glyph) {
    case "running":
      return (
        <span className={box} data-session-glyph="running">
          <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-primary" />
        </span>
      );
    case "waiting":
      return (
        <span className={box} data-session-glyph="waiting">
          <CircleDot aria-hidden className="size-3 text-info" />
        </span>
      );
    case "error":
      return (
        <span className={box} data-session-glyph="error">
          <TriangleAlert aria-hidden className="size-3 text-destructive" />
        </span>
      );
    case "connecting":
      return (
        <span className={box} data-session-glyph="connecting">
          <LoaderCircle aria-hidden className="size-2.5 animate-spin text-muted-foreground/50" />
        </span>
      );
    case "idle":
      return (
        <span className={box} data-session-glyph="idle">
          <Circle aria-hidden className="size-2 text-muted-foreground/60" />
        </span>
      );
  }
}

/**
 * What the thread's turns changed, as a compact `+8 −1` after the title —
 * main tallies the diffs the agent *reported* onto the row
 * (`Session.changedFiles/insertions/deletions`). Review reads git instead, so
 * the two can differ (the person edited a file too, or the agent wrote one
 * without reporting it); the hint says which count this is. A side that is
 * zero is not drawn — a red `−0` reads as a removal — and nothing at all is
 * drawn while every count is zero. A click opens the Review tab in this
 * session's explorer.
 */
function ChangeCounts({ session, onOpen }: { session: Session; onOpen: () => void }) {
  const { changedFiles, insertions, deletions } = session;
  if (changedFiles === 0 && insertions === 0 && deletions === 0) {
    return null;
  }
  const files = `${changedFiles} ${changedFiles === 1 ? "file" : "files"} changed`;
  return (
    <TooltipHint content={`${REPORTED_HINT} — Review shows the working tree`}>
      <button
        aria-label={`Review changes: ${files}, ${insertions} added, ${deletions} removed. ${REPORTED_HINT}; Review shows the working tree`}
        className="flex h-4 shrink-0 items-center gap-0.5 rounded-sm px-0.5 font-mono text-[10px] leading-none tabular-nums hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        data-session-changes
        onClick={(event) => {
          event.stopPropagation();
          onOpen();
        }}
        type="button"
      >
        {insertions > 0 ? <span className="text-success">+{insertions}</span> : null}
        {deletions > 0 ? <span className="text-destructive">−{deletions}</span> : null}
        {insertions === 0 && deletions === 0 ? (
          <span className="text-muted-foreground">{changedFiles}f</span>
        ) : null}
      </button>
    </TooltipHint>
  );
}

const REPORTED_HINT = "Edits the agent reported this session";

/**
 * Where the thread writes, when that is worth saying: a worktree, or a branch
 * that is not the project's own. Nothing at all otherwise — a glyph on every
 * row is a glyph that says nothing (`lib/git-mode.ts`).
 */
function GitGlyph({ session }: { session: Session }) {
  const info = useProjectGitInfo(session.projectId);
  const glyph = gitGlyphFor(session, info);
  if (!glyph) {
    return null;
  }
  const Icon = glyph === "worktree" ? GitFork : GitBranch;
  return (
    <span className="flex size-4 shrink-0 items-center justify-center self-center leading-none text-muted-foreground">
      <Icon aria-label={gitGlyphLabel(session)} className="size-3" />
    </span>
  );
}

import { useState } from "react";
import {
  Archive,
  ArchiveRestore,
  Circle,
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

  const startRename = () => {
    setDraft(session.title);
    setEditing(true);
  };
  const commitRename = () => {
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
      <MenuItem icon={<Pencil />} label="Rename" onSelect={startRename} />
      <MenuItem
        icon={session.archived ? <ArchiveRestore /> : <Archive />}
        label={session.archived ? "Unarchive" : "Archive"}
        onSelect={() => void archive(session.id, !session.archived)}
      />
      <MenuItem
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
            selected
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "hover:bg-sidebar-accent/60",
          )}
          data-pinned={session.pinned ? "" : undefined}
          data-session-row={session.id}
          data-status={session.status}
        >
          <StateGlyph status={session.status} />
          {editing ? (
            <input
              aria-label="Session title"
              autoFocus
              className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
              onBlur={commitRename}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  commitRename();
                } else if (event.key === "Escape") {
                  setEditing(false);
                }
              }}
              value={draft}
            />
          ) : (
            <button
              className="min-w-0 flex-1 truncate text-left text-[13px]"
              onClick={onSelect}
              onDoubleClick={startRename}
              title={projectName ? `${session.title} — ${projectName}` : session.title}
              type="button"
            >
              {session.title}
              {showBranch && session.branch ? (
                <span className="ml-1.5 text-[11px] text-muted-foreground" data-session-branch>
                  {session.branch}
                </span>
              ) : null}
            </button>
          )}
          {projectName ? (
            <span
              className="max-w-[40%] shrink-0 truncate text-[11px] text-muted-foreground/70"
              data-session-project
            >
              {projectName}
            </span>
          ) : null}
          <GitGlyph session={session} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label={`${session.title} actions`}
                className="size-5 shrink-0 text-muted-foreground opacity-0 group-hover/session:opacity-100 data-[state=open]:opacity-100"
                size="icon-xs"
                variant="ghost"
              >
                <MoreHorizontal className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-40">
              <MenuKind.Provider value="dropdown">{menuItems}</MenuKind.Provider>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-40">
        <MenuKind.Provider value="context">{menuItems}</MenuKind.Provider>
      </ContextMenuContent>
    </ContextMenu>
  );
}

/**
 * The state, as the one mark on the row that is always drawn: a hollow circle
 * for a thread with nothing to say, a pulsing dot while a turn streams, an
 * amber triangle when the agent is blocked on the person and a red one when
 * the last turn failed (`lib/sidebar.ts` owns the mapping, and the two
 * triangles differ only in their token).
 */
function StateGlyph({ status }: { status: SessionStatus }) {
  const glyph = sessionGlyphFor(status);
  const label = SESSION_GLYPH_LABELS[glyph];
  const box = "flex size-4 shrink-0 items-center justify-center";
  switch (glyph) {
    case "running":
      return (
        <span className={box} data-session-glyph="running">
          <span
            aria-label={label}
            className="size-2 animate-pulse rounded-full bg-primary"
            role="img"
          />
        </span>
      );
    case "waiting":
      return (
        <span className={box} data-session-glyph="waiting">
          <TriangleAlert
            aria-label={label}
            className="size-3.5 text-[color:var(--foreground-warning)]"
          />
        </span>
      );
    case "error":
      return (
        <span className={box} data-session-glyph="error">
          <TriangleAlert aria-label={label} className="size-3.5 text-destructive" />
        </span>
      );
    case "connecting":
      return (
        <span className={box} data-session-glyph="connecting">
          <LoaderCircle aria-label={label} className="size-3 animate-spin text-muted-foreground/50" />
        </span>
      );
    case "idle":
      return (
        <span className={box} data-session-glyph="idle">
          <Circle aria-label={label} className="size-2.5 text-muted-foreground/60" />
        </span>
      );
  }
}

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
    <span className="flex size-4 shrink-0 items-center justify-center text-muted-foreground">
      <Icon aria-label={gitGlyphLabel(session)} className="size-3" />
    </span>
  );
}

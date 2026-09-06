import { createContext, useContext, useState } from "react";
import {
  Archive,
  ChevronRight,
  Folder,
  GitBranch,
  GitFork,
  Loader2,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@renderer/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { gitGlyphFor, gitGlyphLabel, useProjectGitInfo } from "@renderer/lib/git-mode";
import { useProjects } from "@renderer/state/projects";
import { useProjectSessions, useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

/** Codex shows this many threads per project before `Show more`. */
const VISIBLE_SESSIONS = 5;

/**
 * A project and the sessions under it. Collapsible, with the session's status
 * as a trailing glyph — Codex's convention, and the fastest way to see which
 * thread is still working.
 */
export function ProjectRow({ project }: { project: Project }) {
  const activeProjectId = useProjects((state) => state.activeId);
  const setActiveProject = useProjects((state) => state.setActive);
  const collapsed = useProjects((state) => state.collapsed.has(project.id));
  const toggleCollapsed = useProjects((state) => state.toggleCollapsed);
  const removeProject = useProjects((state) => state.remove);
  const sessions = useProjectSessions(project.id);
  const activeSessionId = useSessions((state) => state.activeId);
  const selectSession = useSessions((state) => state.select);
  const setActiveSession = useSessions((state) => state.setActive);
  const [showAll, setShowAll] = useState(false);

  const selected = activeProjectId === project.id;
  const visible = showAll ? sessions : sessions.slice(0, VISIBLE_SESSIONS);
  const hidden = sessions.length - visible.length;

  return (
    <div className="group/project">
      <div
        className={cn(
          "flex items-center gap-1 rounded-md pr-1 pl-1 transition-colors",
          selected && activeSessionId === null ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60",
        )}
      >
        <button
          aria-expanded={!collapsed}
          aria-label={collapsed ? `Expand ${project.name}` : `Collapse ${project.name}`}
          className="flex size-5 shrink-0 items-center justify-center text-muted-foreground"
          onClick={() => toggleCollapsed(project.id)}
          type="button"
        >
          <ChevronRight
            className={cn("size-3.5 transition-transform", !collapsed && "rotate-90")}
          />
        </button>
        <button
          className="flex h-7 min-w-0 flex-1 items-center gap-2 text-left text-[13px]"
          onClick={() => {
            setActiveProject(project.id);
            setActiveSession(null);
          }}
          title={project.path}
          type="button"
        >
          <Folder className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{project.name}</span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              aria-label={`${project.name} actions`}
              className="size-6 shrink-0 text-muted-foreground opacity-0 group-hover/project:opacity-100 data-[state=open]:opacity-100"
              size="icon-xs"
              variant="ghost"
            >
              <MoreHorizontal className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-44">
            <DropdownMenuItem
              onSelect={() => {
                setActiveProject(project.id);
                setActiveSession(null);
              }}
            >
              New chat here
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void navigator.clipboard.writeText(project.path)}>
              Copy path
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                void window.hardcore.shell.showItemInFolder({ path: project.path });
              }}
            >
              Reveal in Finder
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => void removeProject(project.id)}>
              Remove from Hardcore
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {collapsed ? null : (
        <div className="mt-0.5 mb-1 ml-[26px] flex flex-col gap-px border-l border-sidebar-border pl-2">
          {sessions.length === 0 ? (
            <p className="flex h-7 items-center text-xs text-muted-foreground">No sessions yet</p>
          ) : (
            visible.map((session) => (
              <SessionRow
                key={session.id}
                onSelect={() => selectSession(session.id)}
                selected={session.id === activeSessionId}
                session={session}
              />
            ))
          )}
          {hidden > 0 ? (
            <button
              className="rounded-md px-2 py-1 text-left text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
              onClick={() => setShowAll(true)}
              type="button"
            >
              Show {hidden} more
            </button>
          ) : showAll && sessions.length > VISIBLE_SESSIONS ? (
            <button
              className="rounded-md px-2 py-1 text-left text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
              onClick={() => setShowAll(false)}
              type="button"
            >
              Show less
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

/**
 * One thread. The trailing glyph is Codex's: a spinner while the agent
 * works, a worktree glyph when the session runs in one, a branch glyph
 * when it runs on a branch of the checkout, nothing for a plain directory.
 */
function SessionRow({
  session,
  selected,
  onSelect,
}: {
  session: Session;
  selected: boolean;
  onSelect: () => void;
}) {
  const rename = useSessions((state) => state.rename);
  const archive = useSessions((state) => state.archive);
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

  const busy =
    session.status === "running" || session.status === "waiting" || session.status === "connecting";

  const menuItems = (
    <>
      <MenuItemBoth icon={<Pencil />} label="Rename" onSelect={startRename} />
      <MenuItemBoth
        icon={<Archive />}
        label="Archive"
        onSelect={() => void archive(session.id, true)}
      />
      <MenuItemBoth
        label="Copy path"
        onSelect={() => void navigator.clipboard.writeText(session.cwd)}
      />
      <Separator />
      <MenuItemBoth
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
          data-session-row={session.id}
          data-status={session.status}
        >
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
              title={session.title}
              type="button"
            >
              {session.title}
            </button>
          )}
          <span className="flex size-4 shrink-0 items-center justify-center text-muted-foreground">
            {busy ? <Loader2 aria-label="Working" className="size-3 animate-spin" /> : <SessionGlyph session={session} />}
          </span>
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
              <MenuContext.Provider value="dropdown">{menuItems}</MenuContext.Provider>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-40">
        <MenuContext.Provider value="context">{menuItems}</MenuContext.Provider>
      </ContextMenuContent>
    </ContextMenu>
  );
}

/*
 * The same items serve the `…` dropdown and the right-click menu. Radix's
 * two menus want their own item components, so a tiny context picks the
 * right one and the list is written once.
 */
const MenuContext = createContext<"dropdown" | "context">("dropdown");

function MenuItemBoth({
  icon,
  label,
  onSelect,
  destructive,
}: {
  icon?: React.ReactNode;
  label: string;
  onSelect: () => void;
  destructive?: boolean;
}) {
  const kind = useContext(MenuContext);
  const variant = destructive ? "destructive" : "default";
  return kind === "dropdown" ? (
    <DropdownMenuItem onSelect={onSelect} variant={variant}>
      {icon}
      {label}
    </DropdownMenuItem>
  ) : (
    <ContextMenuItem onSelect={onSelect} variant={variant}>
      {icon}
      {label}
    </ContextMenuItem>
  );
}

function Separator() {
  const kind = useContext(MenuContext);
  return kind === "dropdown" ? <DropdownMenuSeparator /> : <ContextMenuSeparator />;
}

/**
 * Codex's trailing glyph when nothing is running: whatever the session's git
 * mode is worth saying (`@renderer/lib/git-mode.ts`) — a worktree, a branch
 * that is not the project's own, or nothing.
 */
function SessionGlyph({ session }: { session: Session }) {
  const info = useProjectGitInfo(session.projectId);
  const glyph = gitGlyphFor(session, info);
  if (!glyph) {
    return null;
  }
  const Icon = glyph === "worktree" ? GitFork : GitBranch;
  return <Icon aria-label={gitGlyphLabel(session)} className="size-3" />;
}

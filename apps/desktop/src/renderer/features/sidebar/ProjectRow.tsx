import { ChevronRight, Folder, GitBranch, Loader2, MoreHorizontal } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { useProjects } from "@renderer/state/projects";
import { useProjectSessions, useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

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
  const setActiveSession = useSessions((state) => state.setActive);

  const selected = activeProjectId === project.id;

  return (
    <div className="group/project">
      <div
        className={cn(
          "flex items-center gap-1 rounded-md pr-1 pl-1 transition-colors",
          selected ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60",
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
          className="flex min-w-0 flex-1 items-center gap-2 py-1.5 text-left text-sm"
          onClick={() => setActiveProject(project.id)}
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
            <p className="py-1.5 text-xs text-muted-foreground">No sessions yet</p>
          ) : (
            sessions.map((session) => (
              <SessionRow
                key={session.id}
                onSelect={() => setActiveSession(session.id)}
                selected={session.id === activeSessionId}
                session={session}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function SessionRow({
  session,
  selected,
  onSelect,
}: {
  session: Session;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1 text-left text-[13px] transition-colors",
        selected ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60",
      )}
      onClick={onSelect}
      type="button"
    >
      <span className="min-w-0 flex-1 truncate">{session.title}</span>
      {session.status === "running" ? (
        <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />
      ) : session.gitMode === "worktree" ? (
        <GitBranch className="size-3 shrink-0 text-muted-foreground" />
      ) : null}
    </button>
  );
}

import { useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { ChevronRight, Plus, Search } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@renderer/components/ui/context-menu";
import { MenuKind } from "@renderer/features/sidebar/menu";
import { ProjectMenuItems } from "@renderer/features/sidebar/project-menu";
import { SessionRow } from "@renderer/features/sidebar/SessionRow";
import { SidebarFilterMenu } from "@renderer/features/sidebar/SidebarFilterMenu";
import type { SidebarSection } from "@renderer/lib/sidebar";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings, useSidebarSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";

/**
 * One section of the sidebar: a grey header and a flat list of threads under
 * it (`lib/sidebar.ts` decides which sections exist and what is in them).
 *
 * The header is the project — its name, its collapse, and the three controls
 * the design gives it: `+` starts a thread in *this* project, the search
 * glyph opens the palette with this project's name already typed, and the
 * sliders open the filter menu. Everything else a project can do is a
 * right-click away (and in the filter menu's `Project…`), because a header
 * with five buttons on it is not a header.
 *
 * `Pinned` and the one flat list `Group by › None` produces are sections too,
 * with no project behind them: no `+`, nothing to collapse into a preference,
 * and — for the flat list — the sliders, so the grouping that hid every
 * project header can still be changed back.
 */
export function SessionSection({ section }: { section: SidebarSection }) {
  const project = section.project;
  const projects = useProjects(useShallow((state) => state.projects));
  const activeProjectId = useProjects((state) => state.activeId);
  const setActiveProject = useProjects((state) => state.setActive);
  const renameProject = useProjects((state) => state.rename);
  const activeSessionId = useSessions((state) => state.activeId);
  const selectSession = useSessions((state) => state.select);
  const setActiveSession = useSessions((state) => state.setActive);
  const filters = useSidebarSettings();
  const setSidebar = useSettings((state) => state.setSidebar);
  const openCommandPalette = useUi((state) => state.openCommandPalette);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(section.name);

  // Only a project's section has somewhere to file a collapse, and only a
  // project's header is worth collapsing: `Pinned` is there because something
  // is in it, and the flat list is the whole list.
  const collapsible = project !== null;
  const collapsed = collapsible && filters.collapsedProjects.includes(section.id);
  const active = project !== null && project.id === activeProjectId;

  const toggle = () => {
    if (!project) {
      return;
    }
    void setSidebar({
      collapsedProjects: collapsed
        ? filters.collapsedProjects.filter((id) => id !== project.id)
        : [...filters.collapsedProjects, project.id],
    });
  };

  const newHere = () => {
    if (project) {
      setActiveProject(project.id);
      setActiveSession(null);
    }
  };

  const startRename = () => {
    setDraft(section.name);
    setEditing(true);
  };
  const commitRename = () => {
    setEditing(false);
    if (project && draft.trim() && draft.trim() !== project.name) {
      void renameProject(project.id, draft.trim());
    }
  };

  const header = (
    <div
      className="group/section flex h-7 items-center gap-0.5 rounded-md pr-0.5 pl-2"
      data-sidebar-section-header
    >
      {editing ? (
        <input
          aria-label="Project name"
          autoFocus
          className="min-w-0 flex-1 bg-transparent text-[11px] font-medium outline-none"
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
          aria-expanded={collapsible ? !collapsed : undefined}
          aria-label={
            collapsible ? (collapsed ? `Expand ${section.name}` : `Collapse ${section.name}`) : undefined
          }
          className="flex min-w-0 flex-1 items-center gap-1 text-left"
          disabled={!collapsible}
          onClick={toggle}
          title={project?.path ?? section.name}
          type="button"
        >
          <span className="truncate text-[11px] font-medium text-muted-foreground">
            {section.name}
          </span>
          {collapsible ? (
            <ChevronRight
              className={cn(
                "size-3 shrink-0 text-muted-foreground/70 transition-transform",
                !collapsed && "rotate-90",
              )}
            />
          ) : null}
        </button>
      )}

      {project ? (
        <>
          {/* `+` is on every project header; search and the sliders join it
              on hover, and stay out for the active project. */}
          <Button
            aria-label={`New chat in ${project.name}`}
            className="size-5 shrink-0 text-muted-foreground"
            onClick={newHere}
            size="icon-xs"
            variant="ghost"
          >
            <Plus className="size-3" />
          </Button>
          <div
            className={cn(
              "flex shrink-0 items-center gap-0.5",
              active
                ? "opacity-100"
                : "opacity-0 group-hover/section:opacity-100 group-focus-within/section:opacity-100",
            )}
          >
            <Button
              aria-label={`Search ${project.name}`}
              className="size-5 shrink-0 text-muted-foreground"
              onClick={() => openCommandPalette(project.name)}
              size="icon-xs"
              variant="ghost"
            >
              <Search className="size-3" />
            </Button>
            <SidebarFilterMenu onRenameProject={startRename} project={project} />
          </div>
        </>
      ) : section.kind === "all" ? (
        <SidebarFilterMenu onRenameProject={() => undefined} project={null} />
      ) : null}
    </div>
  );

  return (
    <section
      className="mt-2 first:mt-0"
      data-sidebar-section={section.id}
      data-sidebar-section-active={active ? "" : undefined}
      data-sidebar-section-collapsed={collapsed ? "" : undefined}
    >
      {project ? (
        <ContextMenu>
          <ContextMenuTrigger asChild>{header}</ContextMenuTrigger>
          <ContextMenuContent className="w-48">
            <MenuKind.Provider value="context">
              <ProjectMenuItems onRename={startRename} project={project} />
            </MenuKind.Provider>
          </ContextMenuContent>
        </ContextMenu>
      ) : (
        header
      )}

      {collapsed ? null : (
        <div className="mt-0.5 flex flex-col gap-px">
          {section.sessions.length === 0 ? (
            <p className="flex h-7 items-center px-2 text-xs text-muted-foreground">
              No sessions yet
            </p>
          ) : (
            section.sessions.map((session) => (
              <SessionRow
                key={session.id}
                onSelect={() => selectSession(session.id)}
                projectName={
                  // A pinned row has left its project's section, and a flat
                  // list has no section to say it — so the row says it.
                  section.kind === "project"
                    ? undefined
                    : projects.find((candidate) => candidate.id === session.projectId)?.name
                }
                selected={session.id === activeSessionId}
                session={session}
                showBranch={filters.showBranch}
              />
            ))
          )}
        </div>
      )}
    </section>
  );
}

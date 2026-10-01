import { useShallow } from "zustand/react/shallow";
import { ChevronRight, Plus } from "lucide-react";
import { cn } from "cn";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { Button } from "@renderer/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@renderer/components/ui/context-menu";
import { MenuKind } from "@renderer/features/sidebar/menu";
import { ProjectMenuItems } from "@renderer/features/sidebar/project-menu";
import { SessionRow, StateGlyph } from "@renderer/features/sidebar/SessionRow";
import type { SidebarSection } from "@renderer/lib/sidebar";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings, useSidebarSettings } from "@renderer/state/settings";

/**
 * One section of the sidebar: a grey header and a flat list of threads under
 * it (`lib/sidebar.ts` decides which sections exist and what is in them).
 *
 * The header is the project — its name, its collapse, and one control: `+`,
 * a thread in *this* project. Everything else a project can do is a
 * right-click away, because a header with four buttons on it is not a header.
 * Search and the filter menu are the panel's, in its own header
 * (`Sidebar.tsx`): the palette searches every thread and the filters are
 * `settings.sidebar`, so neither was ever a per-project control.
 *
 * `Pinned` and the one flat list `Group by › None` produces are sections too,
 * with no project behind them: no `+`, and nothing to collapse into a
 * preference.
 */
export function SessionSection({ section }: { section: SidebarSection }) {
  const project = section.project;
  const projects = useProjects(useShallow((state) => state.projects));
  const activeProjectId = useProjects((state) => state.activeId);
  const setActiveProject = useProjects((state) => state.setActive);
  const activeSessionId = useSessions((state) => state.activeId);
  const selectSession = useSessions((state) => state.select);
  const setActiveSession = useSessions((state) => state.setActive);
  const filters = useSidebarSettings();
  const setSidebar = useSettings((state) => state.setSidebar);

  // Only a project's section has somewhere to file a collapse, and only a
  // project's header is worth collapsing: `Pinned` is there because something
  // is in it, and the flat list is the whole list.
  const collapsible = project !== null;
  const collapsed = collapsible && filters.collapsedProjects.includes(section.id);
  const active = project !== null && project.id === activeProjectId;

  // A collapsed section hides its rows, and with them the one thing a sidebar exists to surface: a
  // thread that needs the person. The header carries the strongest state among the hidden rows
  // (waiting over running), in the rows' own glyph; an expanded section shows the rows themselves.
  const hidden = collapsed
    ? section.sessions.some((row) => row.status === "waiting")
      ? ("waiting" as const)
      : section.sessions.some((row) => row.status === "running")
        ? ("running" as const)
        : null
    : null;
  const hiddenCount = hidden ? section.sessions.filter((row) => row.status === hidden).length : 0;

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

  const header = (
    <div
      className="flex h-7 items-center gap-0.5 rounded-md pr-0.5 pl-2"
      data-sidebar-section-header
    >
      {/* Named for the section, always: the state is aria-expanded's to say, not the name's. */}
      <button
        aria-expanded={collapsible ? !collapsed : undefined}
        className="flex min-w-0 flex-1 items-center gap-1 text-left"
        disabled={!collapsible}
        onClick={toggle}
        type="button"
      >
        {/* The project's folder, on the name rather than the button: the kit
            holds a hint back from an expanded control, and an open section's
            header is one. `Pinned` and the flat list have no folder to show. */}
        <TooltipHint content={project?.path}>
          <span className="truncate text-[11px] font-medium text-muted-foreground">
            {section.name}
          </span>
        </TooltipHint>
        {collapsible ? (
          <ChevronRight
            className={cn(
              "size-3 shrink-0 text-muted-foreground/70 transition-transform",
              !collapsed && "rotate-90",
            )}
          />
        ) : null}
      </button>

      {hidden ? (
        <span
          aria-label={`${hiddenCount} ${hiddenCount === 1 ? "thread" : "threads"} ${hidden === "waiting" ? "waiting for you" : "working"}`}
          className="flex shrink-0 items-center"
          data-sidebar-section-state={hidden}
          role="img"
        >
          <StateGlyph status={hidden} />
        </span>
      ) : null}

      {project ? (
        /* `+` is the header's one control, and it is always there. The search
           glyph and the sliders that used to join it on hover have moved to
           the panel's own header: neither was ever about one project — the
           palette searches every thread and the filters are global — and a
           control that appears on hover is one nobody finds. */
        <Button
          aria-label={`New session in ${project.name}`}
          className="size-5 shrink-0 text-muted-foreground"
          onClick={newHere}
          size="icon-xs"
          variant="ghost"
        >
          <Plus className="size-3" />
        </Button>
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
              <ProjectMenuItems project={project} />
            </MenuKind.Provider>
          </ContextMenuContent>
        </ContextMenu>
      ) : (
        header
      )}

      {collapsed ? null : (
        <div className="mt-0.5 flex flex-col gap-px">
          {section.sessions.map((session) => (
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
          ))}
        </div>
      )}
    </section>
  );
}

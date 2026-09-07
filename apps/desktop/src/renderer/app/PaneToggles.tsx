/**
 * The two buttons that open and close the side panes.
 *
 * They live here rather than in either feature because the sidebar's collapse
 * is drawn in two places: at the right end of the sidebar's title strip (the
 * traffic lights' row, level with the session's bar) while the sidebar is
 * open, and at the far left of the session's title bar once it is gone. The
 * explorer's sits on the right of that title bar whatever the explorer is
 * doing — and is absent entirely while no project is selected, since there is
 * then no explorer to toggle. One component, so the placements cannot drift.
 */
import { PanelLeft, PanelRight } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@renderer/components/ui/tooltip";
import { useExplorer } from "@renderer/state/explorer";
import { useActiveProject } from "@renderer/state/projects";
import { useSettings } from "@renderer/state/settings";

/** Show or hide the projects sidebar. */
export function SidebarToggle() {
  const collapsed = useSettings((state) => state.settings?.layout.sidebarCollapsed ?? false);
  const setLayout = useSettings((state) => state.setLayout);
  return (
    <PaneToggle
      active={!collapsed}
      icon={<PanelLeft className="size-3.5" />}
      label="Toggle sidebar"
      onClick={() => void setLayout({ sidebarCollapsed: !collapsed })}
    />
  );
}

/**
 * Show or hide the explorer. The state is the explorer's own and per project
 * (`state/explorer.ts`), so this writes the person's choice for the project
 * they are looking at.
 *
 * Nothing at all without a project: the pane is a view of a directory, and
 * with none bound `Shell` does not render it. A control that collapses
 * something that is not there is a control that does nothing.
 */
export function ExplorerToggle() {
  const hasProject = useActiveProject() !== null;
  const collapsed = useExplorer((state) => state.collapsed);
  const toggle = useExplorer((state) => state.toggleCollapsed);
  if (!hasProject) {
    return null;
  }
  return (
    <PaneToggle
      active={!collapsed}
      icon={<PanelRight className="size-3.5" />}
      label="Toggle explorer"
      onClick={toggle}
    />
  );
}

function PaneToggle({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          aria-label={label}
          aria-pressed={active}
          className={active ? "app-no-drag size-7" : "app-no-drag size-7 text-muted-foreground"}
          onClick={onClick}
          size="icon-sm"
          variant="ghost"
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

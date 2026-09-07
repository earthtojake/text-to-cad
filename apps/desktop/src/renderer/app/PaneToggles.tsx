/**
 * The two buttons that open and close the side panes.
 *
 * They live here rather than in either feature because each is drawn in two
 * places that are the same spot on screen (Codex's rule: a pane's toggle
 * never moves). The sidebar's sits right after the traffic lights: in the
 * sidebar's title strip while it is open, at the left of the session's title
 * bar once it is gone. The explorer's sits at the window's right edge: in the
 * session's title bar while the explorer is shut, at the end of the
 * explorer's tab strip once it is open — and is absent entirely while no
 * project is selected, since there is then no explorer to toggle.
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

/**
 * The two buttons that open and close the side panes.
 *
 * They live here rather than in either feature because both sit in the
 * session's title bar — the sidebar's collapse at its far left, the
 * explorer's at its right — whatever the two panes are doing, and the
 * command palette and the shortcuts reach the same two actions.
 */
import { PanelLeft, PanelRight } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@renderer/components/ui/tooltip";
import { useExplorer } from "@renderer/state/explorer";
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
 */
export function ExplorerToggle() {
  const collapsed = useExplorer((state) => state.collapsed);
  const toggle = useExplorer((state) => state.toggleCollapsed);
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

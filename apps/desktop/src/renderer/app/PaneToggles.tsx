/**
 * The controls of the leftmost title strip, and the explorer's toggle.
 *
 * They live here rather than in either feature because each is drawn in two
 * places that are the same spot on screen (Codex's rule: a control in the
 * title strip never moves). The sidebar's toggle sits right after the traffic
 * lights, with back and forward right after it: in the sidebar's title strip
 * while the sidebar is open, at the left of the session's title bar once it is
 * gone. The explorer's toggle sits at the window's right edge: in the
 * session's title bar while the explorer is shut, at the end of the explorer's
 * tab strip once it is open — and is absent entirely while no project is
 * selected, since there is then no explorer to toggle.
 */
import { ChevronLeft, ChevronRight, PanelLeft, PanelRight } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@renderer/components/ui/tooltip";
import { useExplorer } from "@renderer/state/explorer";
import { useHistory, useHistoryReach } from "@renderer/state/history";
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
  const ready = useExplorer((state) => state.ready);
  const toggle = useExplorer((state) => state.toggleCollapsed);
  if (!hasProject) {
    return null;
  }
  return (
    <PaneToggle
      active={!collapsed}
      // The strip's readiness, on the one control that is in the document
      // whether the pane is open or shut. A closed pane is not rendered at
      // all, so this is the only place "the strip has loaded this project's
      // tabs" can be read from outside — which is what the e2e suites wait
      // for before opening anything (a tab opened mid-restore is a tab the
      // restore overwrites).
      attributes={{ "data-explorer-ready": String(ready) }}
      icon={<PanelRight className="size-3.5" />}
      label="Toggle explorer"
      onClick={toggle}
    />
  );
}

/**
 * Back and forward through the top level: a project's new-session screen and
 * its threads (`state/history.ts`).
 *
 * Codex's placement — the two arrows immediately after the sidebar's toggle,
 * moving with it — and Codex's behaviour: muted at the ends of the stack
 * rather than hidden, so the row does not change width and no control ever
 * vanishes from under the pointer. They are the *top level* only; the
 * explorer's tabs have their own strip and are not in this history.
 */
export function HistoryNav() {
  const reach = useHistoryReach();
  const back = useHistory((state) => state.back);
  const forward = useHistory((state) => state.forward);
  return (
    <>
      <NavButton disabled={!reach.back} icon={<ChevronLeft className="size-4" />} label="Back" onClick={back} />
      <NavButton
        disabled={!reach.forward}
        icon={<ChevronRight className="size-4" />}
        label="Forward"
        onClick={forward}
      />
    </>
  );
}

function NavButton({
  icon,
  label,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          aria-label={label}
          className="app-no-drag size-7 text-muted-foreground disabled:opacity-40"
          data-history={label.toLowerCase()}
          disabled={disabled}
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

function PaneToggle({
  icon,
  label,
  active,
  onClick,
  attributes,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
  /** Data attributes for the button; see `ExplorerToggle`'s readiness. */
  attributes?: Record<string, string>;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          {...attributes}
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

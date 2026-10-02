import { Settings, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { CommunityLinks, MadeBy, useFollow } from "../../../file-viewer/navigation/NavbarLinks.jsx";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";

/**
 * Settings: an ordinary popover from the settings cog. Its header is "Settings", the version this
 * host runs in gray beside it (a link to its release notes), and the close X at its right end; its footer, under a rule, "Made by
 * @…" (the host's X account) at the left and Discord and GitHub as icon links at the right; between
 * them, `children` — a file's Display sections and the host's own settings in the
 * viewer (`DisplayPopover`), the host's own settings alone on the home. It goes as any popover
 * does: Escape, its button, its X, or a press anywhere outside it. It is never taller than the
 * room below it: its sections scroll inside it, between the header and the footer. It closes with no exit
 * animation, so a quick second press always reaches the button.
 * @param {{ links?: import("../../../host/types.js").ViewerLinks, open?: boolean, onOpenChange?(open: boolean): void,
 *   disabled?: boolean, align?: "start" | "center" | "end", children?: import("react").ReactNode }} props
 */
export function SettingsPopover({ links, open, onOpenChange, disabled = false, align = "end", children = null }) {
  const controlled = open !== undefined;
  const follow = useFollow(links);
  return <Popover {...(controlled ? { open: open && !disabled } : {})} onOpenChange={onOpenChange} modal={false}>
    <TooltipHint content="Settings">
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" aria-label="Settings" aria-pressed={controlled ? open : undefined} disabled={disabled}
          className="size-6 text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground">
          <Settings className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent side="bottom" align={align} sideOffset={6} collisionPadding={8}
      aria-label="Settings" data-display-popover=""
      className={cn(FLOATING_SURFACE_CLASS, "flex w-64 max-h-[var(--radix-popover-content-available-height)] flex-col overflow-hidden p-0 text-tiny data-[state=closed]:animate-none!")}>
      <div className={cn("flex h-8 shrink-0 items-center gap-1.5 pl-2.5 pr-1", children ? "border-b border-border" : "")} data-settings-header="">
        <h2 className="text-xs font-semibold text-foreground">Settings</h2>
        {links?.version ? (links.release
          ? <a href={links.release} target="_blank" rel="noreferrer" onClick={follow} aria-label={`Release notes for v${links.version}`}
            className="text-tiny tabular-nums text-muted-foreground underline-offset-2 hover:underline" data-settings-version="">v{links.version}</a>
          : <span className="text-tiny tabular-nums text-muted-foreground" data-settings-version="">v{links.version}</span>) : null}
        <PopoverClose aria-label="Close settings" className={cn(TOOL_PANEL_BUTTON_CLASS, "ml-auto")}>
          <X className="size-3" aria-hidden="true" />
        </PopoverClose>
      </div>
      {children ? <ScrollArea className="min-h-0 flex-1">{children}</ScrollArea> : null}
      {links ? <div className="flex h-8 shrink-0 items-center gap-1.5 border-t border-border pl-2.5 pr-1" data-settings-footer="">
        <span className="text-tiny text-muted-foreground"><MadeBy links={links} /></span>
        <div className="ml-auto flex items-center gap-0.5"><CommunityLinks links={links} /></div>
      </div> : null}
    </PopoverContent>
  </Popover>;
}

export { AppSettingsSections } from "../view-settings/appSettings.jsx";

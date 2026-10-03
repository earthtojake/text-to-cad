import { MessageCircle, Settings, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { CommunityLinks, MadeBy, feedbackUrl, useFollow } from "../../../file-viewer/navigation/NavbarLinks.jsx";
import { FileSheetButtonRow, FileSheetSettingsSection } from "../inspector/FileSheet.js";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";
import { AppSettingsSections } from "../view-settings/appSettings.jsx";

const NONE = Object.freeze([]);

/**
 * Settings: the person's own settings, one popover wherever it is reached — the viewer's navbar
 * (`CadViewer` hands it to FileViewer as `settings`) and the home, under its wordmark
 * (`ModelLibrary`) — so the two read the same. A press on the settings cog opens it. Its header is
 * "Settings", the version this host runs in gray beside it (a link to its release notes), and the
 * close X at its right end; its footer, under a rule, "Made by @…" (the host's X account) at the
 * left and Discord and GitHub as icon links at the right; between them, the host's settings
 * (`appSettings`), a section for each `section` they name, then Share Feedback, where the host has a
 * tracker: one button, a new issue titled "Feedback: " naming the version and the `platform`
 * (`feedbackUrl`). Nothing of a file: a file's view is its Display panel's. It goes as any popover
 * does: Escape, its button, its X, or a press anywhere
 * outside it. It is never taller than the room below it: its sections scroll inside it, between
 * the header and the footer. It closes with no exit animation, so a quick second press always
 * reaches the button.
 * @param {{ links?: import("../../../host/types.js").ViewerLinks,
 *   appSettings?: readonly import("../../../file-viewer/types.js").AppSetting[],
 *   platform?: string, align?: "start" | "center" | "end" }} props
 *   `platform`: the host's `environment.platform`, which Share Feedback's issue names. `align`: how
 *   it lines up with the cog — its right end in the navbar, its centre on the home.
 */
export function SettingsPopover({ links, appSettings = NONE, platform, align = "end" }) {
  const follow = useFollow(links);
  const feedback = links ? feedbackUrl(links, platform) : "";
  const sections = appSettings.length > 0 || Boolean(feedback);
  return <Popover modal={false}>
    <TooltipHint content="Settings">
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" aria-label="Settings"
          className="size-6 text-muted-foreground hover:text-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground">
          <Settings className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent side="bottom" align={align} sideOffset={6} collisionPadding={8}
      aria-label="Settings" data-settings-popover=""
      className={cn(FLOATING_SURFACE_CLASS, "flex w-64 max-h-[var(--radix-popover-content-available-height)] flex-col overflow-hidden p-0 text-tiny data-[state=closed]:animate-none!")}>
      <div className={cn("flex h-8 shrink-0 items-center gap-1.5 pl-2.5 pr-1", sections ? "border-b border-border" : "")} data-settings-header="">
        <h2 className="text-xs font-semibold text-foreground">Settings</h2>
        {links?.version ? (links.release
          ? <a href={links.release} target="_blank" rel="noreferrer" onClick={follow} aria-label={`Release notes for v${links.version}`}
            className="text-tiny tabular-nums text-muted-foreground underline-offset-2 hover:underline" data-settings-version="">v{links.version}</a>
          : <span className="text-tiny tabular-nums text-muted-foreground" data-settings-version="">v{links.version}</span>) : null}
        <PopoverClose aria-label="Close settings" className={cn(TOOL_PANEL_BUTTON_CLASS, "ml-auto")}>
          <X className="size-3" aria-hidden="true" />
        </PopoverClose>
      </div>
      {sections ? <ScrollArea className="min-h-0 flex-1"><AppSettingsSections appSettings={appSettings}>
        {feedback ? <FileSheetSettingsSection sectionId="share-feedback" title="Share Feedback">
          <FileSheetButtonRow>
            <Button asChild type="button" variant="outline" size="sm" className="h-7 gap-1.5 px-2 text-tiny font-normal">
              <a href={feedback} target="_blank" rel="noreferrer" onClick={follow} data-link="feedback">
                <MessageCircle className="size-3.5" aria-hidden="true" />Open a GitHub issue
              </a>
            </Button>
          </FileSheetButtonRow>
        </FileSheetSettingsSection> : null}
      </AppSettingsSections></ScrollArea> : null}
      {links ? <div className="flex h-8 shrink-0 items-center gap-1.5 border-t border-border pl-2.5 pr-1" data-settings-footer="">
        <span className="text-tiny text-muted-foreground"><MadeBy links={links} /></span>
        <div className="ml-auto flex items-center gap-0.5"><CommunityLinks links={links} /></div>
      </div> : null}
    </PopoverContent>
  </Popover>;
}

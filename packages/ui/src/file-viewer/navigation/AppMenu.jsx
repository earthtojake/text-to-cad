import { ArrowLeft, MessageCircle } from "lucide-react";
import { Fragment } from "react";

import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { cn } from "@text-to-cad/ui/utils";

import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";

import { DiscordMark, GitHubMark } from "./brandMarks.jsx";
import { feedbackUrl, MadeBy, useFollow } from "./NavbarLinks.jsx";

const NONE = Object.freeze([]);

/**
 * The app's menu: what is the person's rather than a file's, one menu wherever it is reached — the
 * navbar's logo, over every file, and the home's cog. First, where it is opened from a file and the
 * host has a home, Back to files (`onHome`). Then the host's on/off settings (`appSettings`: Quick
 * edit, sharing anonymous usage data), checked at the right, which a press turns without closing
 * the menu; then Send feedback (a new issue on the host's tracker, naming the version and the
 * `platform`), GitHub and Discord; and last, in gray, the version this host runs (a link to its
 * release notes) and who made it. Every link opens the host's way (`links.open`).
 *
 * @param {{ trigger: import("react").ReactElement, onHome?: () => void,
 *   links?: import("../../host/types.js").ViewerLinks, appSettings?: readonly import("../types.js").AppSetting[],
 *   platform?: string, align?: "start" | "center" | "end" }} props
 */
export function AppMenu({ trigger, onHome, links, appSettings = NONE, platform, align = "start" }) {
  const follow = useFollow(links);
  const feedback = links ? feedbackUrl(links, platform) : "";
  const outward = [
    feedback ? { id: "feedback", label: "Send feedback", href: feedback, icon: MessageCircle } : null,
    links?.github ? { id: "github", label: "GitHub", href: links.github, icon: GitHubMark } : null,
    links?.discord ? { id: "discord", label: "Discord", href: links.discord, icon: DiscordMark } : null,
  ].filter(Boolean);
  const groups = [
    onHome ? [<DropdownMenuItem key="home" onSelect={onHome} data-menu-home=""><ArrowLeft aria-hidden="true" />Back to files</DropdownMenuItem>] : [],
    appSettings.map(setting => <DropdownMenuCheckboxItem key={setting.id} checked={setting.checked} disabled={setting.disabled}
      onCheckedChange={checked => setting.onCheckedChange(checked === true)} onSelect={event => event.preventDefault()}
      data-app-setting={setting.id}>{setting.label}</DropdownMenuCheckboxItem>),
    outward.map(({ id, label, href, icon: Icon }) => <DropdownMenuItem key={id} asChild>
      <a href={href} target="_blank" rel="noreferrer" onClick={follow} data-link={id}><Icon className="size-3.5" aria-hidden="true" />{label}</a>
    </DropdownMenuItem>),
  ].filter(group => group.length);
  const version = links?.version ? (links.release
    ? <a href={links.release} target="_blank" rel="noreferrer" onClick={follow} className="hover:text-foreground" data-menu-version="">v{links.version}</a>
    : <span data-menu-version="">v{links.version}</span>) : null;
  const madeBy = links?.x ? <MadeBy links={links} /> : null;
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
    <DropdownMenuContent align={align} sideOffset={6} collisionPadding={8} aria-label="Menu" data-app-menu=""
      className={cn(FLOATING_SURFACE_CLASS, "w-60 data-[state=closed]:animate-none!")}>
      {groups.map((group, index) => <Fragment key={index}>{index ? <DropdownMenuSeparator /> : null}{group}</Fragment>)}
      {version || madeBy ? <>
        {groups.length ? <DropdownMenuSeparator /> : null}
        <div className="flex min-w-0 flex-wrap items-center gap-x-1 px-2 py-1.5 text-tiny text-muted-foreground tabular-nums *:whitespace-nowrap" data-menu-footer="">
          {version}{version && madeBy ? <span aria-hidden="true">·</span> : null}{madeBy}
        </div>
      </> : null}
    </DropdownMenuContent>
  </DropdownMenu>;
}

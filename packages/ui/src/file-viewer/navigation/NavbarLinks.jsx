import { Check, CircleCheck, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@text-to-cad/ui/primitives/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { cn } from "@text-to-cad/ui/utils";

import { DiscordMark, GitHubMark } from "./brandMarks.jsx";
import wordmark from "../../assets/logo-cad.svg";

/**
 * The navbar's right end: the version (`v0.7.4`), the same in every app (`ViewerHost.links`, built
 * by `viewerLinks` in `links.js`).
 *
 * It opens a menu of what it is and how to update it — the command for a terminal and the message
 * for an agent, or a line saying how where the host's update is not a command — then the release
 * notes, GitHub and Discord. A host that checked for a newer release says what it found
 * (`links.latest`): a newer one is a dot on the version. Every link opens the host's way: a page that can open one itself follows an
 * ordinary link to a new tab; a page in a frame that cannot hands it to `links.open` (the host's own
 * browser). Copies go through the host's clipboard.
 *
 * @param {object} props
 * @param {import("../../host/types.js").ViewerLinks} props.links
 * @param {import("../../host/types.js").ClipboardPort} props.clipboard
 * @param {(error: Error) => void} [props.onError]
 * @param {"start" | "center" | "end"} [props.align] How the menu lines up with the version: its right
 *   end in the navbar, its centre under the home's wordmark.
 */
export function NavbarLinks({ links, clipboard, onError, align = "end" }) {
  const follow = links.open ? (event) => {
    event.preventDefault();
    const url = event.currentTarget.href;
    void Promise.resolve().then(() => links.open(url)).catch((error) => onError?.(error instanceof Error ? error : new Error(String(error))));
  } : undefined;
  return <VersionMenu links={links} clipboard={clipboard} onFollow={follow} align={align} />;
}

/** One of the menu's links, opened the host's way. */
function MenuLink({ href, icon: Icon = null, onFollow, children }) {
  if (!href) return null;
  return <DropdownMenuItem asChild><a href={href} target="_blank" rel="noreferrer" onClick={onFollow}>
    {Icon ? <Icon className="size-3.5" aria-hidden="true" /> : null}{children}
  </a></DropdownMenuItem>;
}

/** A line to copy — a command, or a message for an agent — with its own Copy button. */
function CopyRow({ label, text, copyLabel, copiedLabel, mono = false, clipboard }) {
  const [status, setStatus] = useState("");
  const reset = useRef(0);
  useEffect(() => () => clearTimeout(reset.current), []);
  const copy = async () => {
    clearTimeout(reset.current);
    try {
      await clipboard.writeText(text);
      setStatus("copied");
      // Only the button's glyph says it worked, and only for a moment: the viewer shows no toasts.
      reset.current = setTimeout(() => setStatus(""), 1600);
    } catch { setStatus("failed"); }
  };
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="px-0.5 text-tiny leading-none text-muted-foreground">{label}</div>
      <div className="flex min-h-8 min-w-0 items-center gap-2 rounded-sm border border-border/60 bg-muted/35 p-1 pl-2">
        {/* Shown verbatim and wrapped, never summarised: it is exactly what the button copies. */}
        <span className={cn("min-w-0 flex-1 break-words text-tiny leading-4 text-foreground", mono && "font-mono")}>{text}</span>
        <Button type="button" variant="ghost" size="icon" onClick={() => void copy()}
          className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm border border-border text-foreground hover:bg-accent hover:text-accent-foreground"
          aria-label={status === "copied" ? copiedLabel : copyLabel}>
          {status === "copied" ? <Check className="size-3" aria-hidden="true" /> : <Copy className="size-3" aria-hidden="true" />}
        </Button>
      </div>
      {status === "failed" ? <div className="px-0.5 text-tiny text-muted-foreground">Copy failed</div> : null}
    </div>
  );
}

/**
 * The version, and how to update it. An update the host found is a dot on the version, as an app
 * marks one in its menu; nothing louder. Open, the menu says where the person stands — the version
 * and that it is up to date, or "Update available" with the step from this version to the new one —
 * then, unless it is up to date, how this host updates. Its links end it: the notes of the release
 * that matters (the new one, while there is one), GitHub and Discord.
 */
function VersionMenu({ links, clipboard, onFollow, align }) {
  const { version, latest, install, release } = links;
  if (!version) return null;
  const update = latest?.newer ? latest : null;
  const upToDate = Boolean(latest) && !update;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="xs" data-navbar-version="" data-update={update ? "" : undefined}
          className="h-6 gap-1.5 rounded-sm px-2 text-tiny tabular-nums text-muted-foreground hover:text-foreground data-[update]:text-foreground"
          aria-label={update ? `Version ${version}, update available` : `Version ${version}`}>
          v{version}
          {update ? <span className="size-1.5 rounded-full bg-blue-500" aria-hidden="true" /> : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} sideOffset={6}
        className="w-60 max-w-[calc(100vw-1rem)] border border-border bg-popover p-2 text-left text-popover-foreground shadow-lg shadow-black/10">
        <div className="flex flex-col gap-3">
          <img src={wordmark} alt="CAD" className="h-5 w-auto self-start px-0.5 select-none" draggable={false} />
          {update ? <div className="flex flex-col gap-1 px-0.5" data-version-update="">
            <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <span className="size-1.5 rounded-full bg-blue-500" aria-hidden="true" />Update available
            </span>
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              v{version} <span aria-label="to">→</span> <span className="text-foreground">v{update.version}</span>
            </span>
          </div> : <div className="flex items-center justify-between gap-2 px-0.5">
            <span className="font-mono text-xs tabular-nums text-foreground">v{version}</span>
            {upToDate ? <span className="flex items-center gap-1 text-tiny text-muted-foreground">
              <CircleCheck className="size-3 text-primary" aria-hidden="true" />Up to date
            </span> : null}
          </div>}
          {upToDate ? null : <>
            {install.command ? <CopyRow label="In your terminal" text={install.command} mono clipboard={clipboard}
              copyLabel="Copy install command" copiedLabel="Install command copied" /> : null}
            {install.prompt ? <CopyRow label="Or ask your agent" text={install.prompt} clipboard={clipboard}
              copyLabel="Copy agent message" copiedLabel="Agent message copied" /> : null}
            {install.message ? <p className="px-0.5 text-tiny leading-4 text-muted-foreground" data-install-message="">{install.message}</p> : null}
          </>}
        </div>
        {/* Edge to edge, outside the content's own padding, with room either side. */}
        <DropdownMenuSeparator className="-mx-2 my-2" />
        <MenuLink href={update ? update.url : release} onFollow={onFollow}>{update ? `What’s new in v${update.version}` : "Release notes"}</MenuLink>
        <MenuLink href={links.github} icon={GitHubMark} onFollow={onFollow}>GitHub</MenuLink>
        <MenuLink href={links.discord} icon={DiscordMark} onFollow={onFollow}>Discord</MenuLink>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

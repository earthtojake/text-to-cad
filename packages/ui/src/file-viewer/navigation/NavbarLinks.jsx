import { Check, CircleCheck, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@text-to-cad/ui/primitives/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";

import { DiscordMark, GitHubMark } from "./brandMarks.jsx";
import wordmark from "../../assets/logo-cad.svg";

/**
 * The navbar's right end: the version, then GitHub and Discord as icons — the same three in every
 * app (`ViewerHost.links`, built by `viewerLinks` in `links.js`).
 *
 * The version opens a menu of what it is and how to update it — the command for a terminal and the
 * message for an agent, or a line saying how where the host's update is not a command — and the
 * release notes. A host that checked for a newer release says so (`links.latest`), and the version
 * then reads "Update". Every link opens the host's way: a page that can open one itself follows an
 * ordinary link to a new tab; a page in a frame that cannot hands it to `links.open` (the host's own
 * browser). Copies go through the host's clipboard.
 *
 * @param {object} props
 * @param {import("../../host/types.js").ViewerLinks} props.links
 * @param {import("../../host/types.js").ClipboardPort} props.clipboard
 * @param {(error: Error) => void} [props.onError]
 */
export function NavbarLinks({ links, clipboard, onError }) {
  const follow = links.open ? (event) => {
    event.preventDefault();
    const url = event.currentTarget.href;
    void Promise.resolve().then(() => links.open(url)).catch((error) => onError?.(error instanceof Error ? error : new Error(String(error))));
  } : undefined;
  return <>
    <VersionMenu links={links} clipboard={clipboard} onFollow={follow} />
    <IconLink href={links.github} label="GitHub" icon={GitHubMark} onFollow={follow} />
    <IconLink href={links.discord} label="Discord" icon={DiscordMark} onFollow={follow} />
  </>;
}

function IconLink({ href, label, icon: Icon, onFollow }) {
  if (!href) return null;
  return <TooltipHint content={label}>
    <Button asChild variant="ghost" size="icon-xs" className="size-6 text-muted-foreground hover:text-foreground">
      <a href={href} target="_blank" rel="noreferrer" aria-label={label} onClick={onFollow} data-navbar-link={label.toLowerCase()}>
        <Icon className="size-3.5" />
      </a>
    </Button>
  </TooltipHint>;
}

function VersionRow({ label, version, action = null }) {
  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5 px-0.5 text-left">
      <span className="text-tiny leading-none text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 text-left font-mono text-xs leading-5 text-foreground tabular-nums">{version}</span>
        {action}
      </div>
    </div>
  );
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
        <span className={cn("min-w-0 max-w-[15.5rem] flex-1 text-tiny leading-4 text-foreground", mono && "font-mono")}>{text}</span>
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

function VersionMenu({ links, clipboard, onFollow }) {
  const { version, latest, install, release } = links;
  if (!version) return null;
  const update = Boolean(latest?.newer);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={update ? "default" : "ghost"} size="xs"
          className={cn("h-6 rounded-sm px-2 text-tiny", !update && "text-muted-foreground tabular-nums hover:text-foreground")}
          aria-label={update ? `Update to ${latest.version}` : `Version ${version}`} data-navbar-version="">
          {update ? "Update" : version}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={6}
        className="w-fit max-w-[calc(100vw-1rem)] border border-border bg-popover p-2 text-left text-popover-foreground shadow-lg shadow-black/10">
        <div className="inline-flex max-w-full flex-col gap-3">
          <img src={wordmark} alt="CAD" className="h-5 w-auto self-start px-0.5 select-none" draggable={false} />
          {update ? (
            <div className="grid w-full min-w-0 grid-cols-2 gap-3">
              <VersionRow label="Current Version" version={version} />
              <VersionRow label="Latest Version" version={latest.version} action={latest.url ? (
                <Button asChild variant="default" size="xs" className="h-4 !min-h-0 rounded-sm !px-1.5 !py-0 text-micro leading-none">
                  <a href={latest.url} target="_blank" rel="noreferrer" onClick={onFollow} aria-label={`Update to ${latest.version}`}>Update</a>
                </Button>
              ) : null} />
            </div>
          ) : <VersionRow label="Current Version" version={version} />}
          {install.command ? <CopyRow label="In your terminal" text={install.command} mono clipboard={clipboard}
            copyLabel="Copy install command" copiedLabel="Install command copied" /> : null}
          {install.prompt ? <CopyRow label="Or ask your agent" text={install.prompt} clipboard={clipboard}
            copyLabel="Copy agent message" copiedLabel="Agent message copied" /> : null}
          {install.message ? <p className="max-w-72 px-0.5 text-tiny leading-4 text-muted-foreground" data-install-message="">{install.message}</p> : null}
          {latest && !latest.newer ? (
            <div className="flex items-center gap-1.5 px-0.5 text-tiny text-muted-foreground">
              <CircleCheck className="size-3 text-primary" aria-hidden="true" />
              <span>You are up to date</span>
            </div>
          ) : null}
        </div>
        {release ? <>
          {/* Edge to edge, outside the content's own padding, with room either side. */}
          <DropdownMenuSeparator className="-mx-2 my-2" />
          <DropdownMenuItem asChild><a href={release} target="_blank" rel="noreferrer" onClick={onFollow}>Release notes</a></DropdownMenuItem>
        </> : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

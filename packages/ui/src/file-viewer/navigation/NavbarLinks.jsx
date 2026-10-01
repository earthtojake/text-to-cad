import { Check, Copy, Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@text-to-cad/ui/primitives/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";

import { DiscordMark, GitHubMark } from "./brandMarks.jsx";
import wordmark from "../../assets/logo-cad.svg";

/**
 * The host's links (`ViewerHost.links`, built by `viewerLinks` in `links.js`), as the viewer shows
 * them. A newer release the host found (`links.latest`) is a blue download button — nothing at all
 * when there is none — whose menu says what is new and how this host updates (`UpdateButton`).
 * GitHub and Discord are icon links (`CommunityLinks`): in the Settings popover's header, beside
 * the version, and under the home's wordmark. Every link opens the host's way: a page that can open
 * one itself follows an ordinary link to a new tab; a page in a frame that cannot hands it to
 * `links.open` (the host's own browser). Copies go through the host's clipboard.
 */

/** How a link is followed: the ordinary way, or through the host's `links.open`. */
function useFollow(links, onError) {
  if (!links?.open) return undefined;
  return (event) => {
    event.preventDefault();
    const url = event.currentTarget.href;
    void Promise.resolve().then(() => links.open(url)).catch((error) => onError?.(error instanceof Error ? error : new Error(String(error))));
  };
}

/**
 * GitHub and Discord, as icon links.
 * @param {{ links: import("../../host/types.js").ViewerLinks, onError?: (error: Error) => void }} props
 */
export function CommunityLinks({ links, onError }) {
  const follow = useFollow(links, onError);
  return <>
    <IconLink href={links.github} label="GitHub" icon={GitHubMark} onFollow={follow} />
    <IconLink href={links.discord} label="Discord" icon={DiscordMark} onFollow={follow} />
  </>;
}

function IconLink({ href, label, icon: Icon, onFollow }) {
  if (!href) return null;
  return <TooltipHint content={label}>
    <Button asChild variant="ghost" size="icon-xs" className="size-6 text-muted-foreground hover:text-foreground">
      <a href={href} target="_blank" rel="noreferrer" aria-label={label} onClick={onFollow} data-link={label.toLowerCase()}>
        <Icon className="size-3.5" />
      </a>
    </Button>
  </TooltipHint>;
}

/**
 * The update, where the host found a newer release: a blue download button whose menu says the
 * step from this version to the new one, how this host updates — the command for a terminal and
 * the message for an agent, or a line saying how where the update is not a command — and what is
 * new. Nothing where there is no update.
 * @param {{ links: import("../../host/types.js").ViewerLinks, clipboard: import("../../host/types.js").ClipboardPort,
 *   onError?: (error: Error) => void, align?: "start" | "center" | "end" }} props
 *   `align`: how the menu lines up with the button — its right end in the navbar, its centre on the home.
 */
export function UpdateButton({ links, clipboard, onError, align = "end" }) {
  const follow = useFollow(links, onError);
  const update = links.version && links.latest?.newer ? links.latest : null;
  if (!update) return null;
  const { version, install } = links;
  return (
    <DropdownMenu>
      <TooltipHint content="Update">
        <DropdownMenuTrigger asChild>
          <Button variant="default" size="icon-xs" aria-label={`Update to ${update.version}`} data-update=""
            className="size-6 bg-blue-500 text-white hover:bg-blue-600 dark:bg-blue-500 dark:hover:bg-blue-400">
            <Download className="size-3.5" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
      </TooltipHint>
      <DropdownMenuContent align={align} sideOffset={6}
        className="w-60 max-w-[calc(100vw-1rem)] border border-border bg-popover p-2 text-left text-popover-foreground shadow-lg shadow-black/10">
        <div className="flex flex-col gap-3">
          <img src={wordmark} alt="CAD" className="h-5 w-auto self-start px-0.5 select-none" draggable={false} />
          <div className="flex flex-col gap-1 px-0.5" data-version-update="">
            <span className="text-xs font-medium text-foreground">Update available</span>
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              v{version} <span aria-label="to">→</span> <span className="text-foreground">v{update.version}</span>
            </span>
          </div>
          {install.command ? <CopyRow label="In your terminal" text={install.command} mono clipboard={clipboard}
            copyLabel="Copy install command" copiedLabel="Install command copied" /> : null}
          {install.prompt ? <CopyRow label="Or ask your agent" text={install.prompt} clipboard={clipboard}
            copyLabel="Copy agent message" copiedLabel="Agent message copied" /> : null}
          {install.message ? <p className="px-0.5 text-tiny leading-4 text-muted-foreground" data-install-message="">{install.message}</p> : null}
        </div>
        {update.url ? <>
          {/* Edge to edge, outside the content's own padding, with room either side. */}
          <DropdownMenuSeparator className="-mx-2 my-2" />
          <DropdownMenuItem asChild><a href={update.url} target="_blank" rel="noreferrer" onClick={follow}>What’s new in v{update.version}</a></DropdownMenuItem>
        </> : null}
      </DropdownMenuContent>
    </DropdownMenu>
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

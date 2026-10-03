import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { DiscordMark, GitHubMark } from "./brandMarks.jsx";
import { issueUrl } from "./links.js";

/**
 * The host's links (`ViewerHost.links`, built by `viewerLinks` in `links.js`), as the viewer shows
 * them. The Settings popover's footer has "Made by @…" (`MadeBy`, the host's X account) at its left and
 * Discord and GitHub (`CommunityLinks`) at its right; the version, beside its title, links its
 * release notes; its Feedback opens a new issue (`feedbackUrl`). GitHub alone (`GitHubLink`)
 * is under the home's wordmark, before Settings. Every link opens the
 * host's way: a page that can open one itself follows an ordinary link to a new tab; a page in a
 * frame that cannot hands it to `links.open` (the host's own browser).
 */

/**
 * How a link is followed: the ordinary way, or through the host's `links.open`.
 * @param {import("../../host/types.js").ViewerLinks | undefined} links
 * @param {(error: Error) => void} [onError]
 */
export function useFollow(links, onError) {
  if (!links?.open) return undefined;
  return (event) => {
    event.preventDefault();
    const url = event.currentTarget.href;
    void Promise.resolve().then(() => links.open(url)).catch((error) => onError?.(error instanceof Error ? error : new Error(String(error))));
  };
}

/**
 * Discord and GitHub, as icon links, in that order (X is "Made by @…", `MadeBy`).
 * @param {{ links: import("../../host/types.js").ViewerLinks, onError?: (error: Error) => void }} props
 */
export function CommunityLinks({ links, onError }) {
  const follow = useFollow(links, onError);
  return <>
    <IconLink href={links.discord} label="Discord" icon={DiscordMark} onFollow={follow} />
    <IconLink href={links.github} label="GitHub" icon={GitHubMark} onFollow={follow} />
  </>;
}

/**
 * GitHub alone, as an icon link: under the home's wordmark, before Settings. It says, in one
 * glance, that the project is open source.
 * @param {{ links: import("../../host/types.js").ViewerLinks, onError?: (error: Error) => void }} props
 */
export function GitHubLink({ links, onError }) {
  const follow = useFollow(links, onError);
  return <IconLink href={links.github} label="GitHub" icon={GitHubMark} onFollow={follow} />;
}

/**
 * Feedback's address: a new issue on the host's tracker (`links.issues`) titled "Feedback: ",
 * blank for the person to finish but for where it came from — the version and the platform. It
 * carries no label: what a person says there may be a bug, a request or a question, and the project
 * has no label for all of them. "" where the host has no tracker.
 * @param {import("../../host/types.js").ViewerLinks} links
 * @param {string} [platform] The host's `environment.platform`.
 */
export function feedbackUrl(links, platform) {
  return issueUrl(links.issues, { title: "Feedback: ", body: "**What happened, or what would you like?**\n\n", about: { CAD: links.version, Platform: platform } });
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
 * Who made it: "Made by @handle", the host's X account, at the left of the Settings popover's footer.
 * @param {{ links: import("../../host/types.js").ViewerLinks, onError?: (error: Error) => void }} props
 */
export function MadeBy({ links, onError }) {
  const follow = useFollow(links, onError);
  const handle = String(links.x || "").replace(/\/+$/, "").split("/").pop();
  if (!links.x || !handle) return null;
  return <a href={links.x} target="_blank" rel="noreferrer" onClick={follow} className="hover:text-foreground" data-link="made-by">Made by @{handle}</a>;
}

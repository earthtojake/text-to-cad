import { MessageCircle } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";

import { useControlUsage } from "../../usage/controls.js";
import { DiscordMark, GitHubMark, XMark } from "./brandMarks.jsx";
import { issueUrl } from "./links.js";

/**
 * The host's links (`ViewerHost.links`, built by `viewerLinks` in `links.js`), as the viewer shows
 * them: Send feedback (`feedbackUrl`), GitHub, Discord and X (`useOutwardLinks`), which are icons in the panel's foot
 * (`../PanelFoot.jsx`: the bottom of the sidebar, on the home and over a document) and, in a host with no home, items
 * of the app menu the logo opens (`AppMenu.jsx`); and in the app menu's footer the version (its release notes) and "Made by @…" (`MadeBy`, the
 * host's X account). Every link opens the host's way: a page that can open one itself follows an ordinary link to a new tab; a page in a
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

/**
 * The host's links out, each as whatever draws it needs: its name, its address, its mark and what a press does (the
 * link followed the host's way, `useFollow`; Send feedback counted, `feedback`). One definition for the app menu's
 * items and the icons in the panel's foot, so both do the same thing. Each null where the host gives no
 * such link.
 * @param {import("../../host/types.js").ViewerLinks | undefined} links
 * @param {string} [platform] The host's `environment.platform`, which Send feedback names.
 * @returns {Record<"github" | "discord" | "x" | "feedback", { id: string, label: string, href: string,
 *   Icon: import("react").ComponentType<any>, onClick(event: import("react").MouseEvent): void } | null>}
 */
export function useOutwardLinks(links, platform) {
  const { t } = useI18n();
  const follow = useFollow(links);
  const usage = useControlUsage();
  const link = (id, label, href, Icon) => (href ? { id, label, href, Icon,
    onClick: event => { if (id === "feedback") usage.used("feedback"); follow?.(event); } } : null);
  return {
    github: link("github", "GitHub", links?.github, GitHubMark),
    discord: link("discord", "Discord", links?.discord, DiscordMark),
    x: link("x", "X", links?.x, XMark),
    feedback: link("feedback", t("menu.feedback"), links ? feedbackUrl(links, platform) : "", MessageCircle),
  };
}

/**
 * Who made it: "Made by @handle", the host's X account, in the app menu's footer.
 * @param {{ links: import("../../host/types.js").ViewerLinks, onError?: (error: Error) => void }} props
 */
export function MadeBy({ links, onError }) {
  const { t } = useI18n();
  const follow = useFollow(links, onError);
  const handle = String(links.x || "").replace(/\/+$/, "").split("/").pop();
  if (!links.x || !handle) return null;
  return <a href={links.x} target="_blank" rel="noreferrer" onClick={follow} className="text-muted-foreground underline-offset-2 outline-none hover:text-foreground hover:underline focus-visible:text-foreground focus-visible:underline" data-link="made-by">{t("menu.madeBy", { handle })}</a>;
}

import { useI18n } from "@text-to-cad/ui/i18n";

import { issueUrl } from "./links.js";

/**
 * The host's links (`ViewerHost.links`, built by `viewerLinks` in `links.js`), as the viewer shows
 * them. The app menu (`AppMenu.jsx`) holds Send feedback (`feedbackUrl`), GitHub and Discord, and
 * in its footer the version (its release notes) and "Made by @…" (`MadeBy`, the host's X account),
 * over a file and on the home alike. Every link opens the host's way: a page that can open one itself follows an ordinary link to a new tab; a page in a
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
 * Who made it: "Made by @handle", the host's X account, in the app menu's footer.
 * @param {{ links: import("../../host/types.js").ViewerLinks, onError?: (error: Error) => void }} props
 */
export function MadeBy({ links, onError }) {
  const { t } = useI18n();
  const follow = useFollow(links, onError);
  const handle = String(links.x || "").replace(/\/+$/, "").split("/").pop();
  if (!links.x || !handle) return null;
  return <a href={links.x} target="_blank" rel="noreferrer" onClick={follow} className="hover:text-foreground" data-link="made-by">{t("menu.madeBy", { handle })}</a>;
}

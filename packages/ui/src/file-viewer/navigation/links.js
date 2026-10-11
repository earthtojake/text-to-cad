/**
 * What the app menu links to, in every app: the running version (its release notes), the
 * source, the community and a new issue. `@text-to-cad/ui/links` — pure, with no imports, so a
 * host's own build configuration and its unit tests read the same defaults the navbar draws. A
 * newer release is not a link: cadgen says so, in the update card (`@text-to-cad/ui/update`).
 *
 * A host supplies the version it runs, and the id of its build where that is not the release's
 * own (`@text-to-cad/ui/build-id`), and hands `viewerLinks(...)` to its `ViewerHost.links`. It
 * may point the links elsewhere (the web reads its build's environment), and say how a link is
 * followed (`open`, for a page in a frame that cannot open one itself). Nothing here fetches or
 * navigates.
 */

export const TEXT_TO_CAD_LINKS = Object.freeze({
  x: "https://x.com/earthtojake",
  github: "https://github.com/earthtojake/text-to-cad",
  discord: "https://discord.gg/5FGB9DwJYU",
  issues: "https://github.com/earthtojake/text-to-cad/issues/new"
});

/** A version as the navbar shows and compares it: `v0.7.4`, or a `refs/tags/` ref, is `0.7.4`. */
export function releaseVersion(value = "") {
  return String(value ?? "").trim().replace(/^refs\/tags\//iu, "").replace(/^v(?=\d)/iu, "");
}

/** A release's notes on its repository: `0.7.4` is tagged `v0.7.4`. */
export function releaseNotesUrl(repository, version) {
  const bare = releaseVersion(version);
  const base = String(repository || "").trim().replace(/\/+$/u, "");
  return bare && base ? `${base}/releases/tag/${encodeURIComponent(`v${bare}`)}` : "";
}

/** The longest address a new issue is opened at: GitHub turns one away not far past 8 KB. */
export const ISSUE_URL_MAX = 6000;

/**
 * A new issue on `issues` (`ViewerLinks.issues`), filled in as `?title=…&labels=…&body=…`; "" without
 * `issues`. The body is `body`, then `about` as a list ("- CAD: 0.7.5", each label with a value),
 * then `details`, fenced. The address never passes `max` characters: the title and the labels are
 * kept whole and count against it, `details` gives way first, from its end, then `body`, each cut
 * marked. Nothing is sent: the person reads the issue, says what they were doing and submits it.
 *
 * `title` is where the issue opens: a person finishing it types after it ("Feedback: "). `labels`
 * are the names of labels the repository has, passed as GitHub's comma-separated `labels`
 * parameter. GitHub applies them only for someone with triage access to the repository and drops
 * them for everyone else, who open the issue unlabelled: a label is a convenience, never a need.
 *
 * @param {string | undefined} issues
 * @param {{ title?: string, labels?: readonly string[], body?: string, about?: Record<string, string | undefined>, details?: string }} [issue]
 * @param {number} [max]
 */
export function issueUrl(issues, { title = "", labels = [], body = "", about = {}, details = "" } = {}, max = ISSUE_URL_MAX) {
  const base = String(issues || "").trim();
  if (!base) return "";
  const named = labels.map((label) => String(label).trim()).filter(Boolean).join(",");
  const address = (text) => {
    const query = new URLSearchParams();
    if (title) query.set("title", title);
    if (named) query.set("labels", named);
    if (text) query.set("body", text);
    const search = query.toString();
    return search ? `${base}${base.includes("?") ? "&" : "?"}${search}` : base;
  };
  const list = Object.entries(about).filter(([, value]) => value).map(([label, value]) => `- ${label}: ${value}`).join("\n");
  const head = [body, list && `**Environment**\n\n${list}`].filter(Boolean).join("\n\n");
  // A fence longer than any run of backticks in the log, so nothing in it closes the block.
  const fenced = (log) => {
    const fence = "`".repeat(Math.max(3, ...Array.from(log.matchAll(/`+/gu), ([run]) => run.length + 1)));
    return `${head}\n\n**Details**\n\n${fence}\n${log}\n${fence}`;
  };
  // The longest cut of `text` whose address fits, found by halves: an address only grows with its
  // text, and no more of it than `max` characters can ever fit.
  const fit = (text, compose) => {
    if (text.length <= max && address(compose(text)).length <= max) return compose(text);
    let low = 0, high = Math.min(text.length - 1, max);
    while (low < high) {
      const middle = Math.ceil((low + high) / 2);
      if (address(compose(cut(text, middle))).length <= max) low = middle; else high = middle - 1;
    }
    return low ? compose(cut(text, low)) : null;
  };
  const log = String(details || "");
  const text = (log ? fit(log, fenced) : null) ?? fit(head, (kept) => kept) ?? "";
  return address(text).length <= max ? address(text) : base;
}

/** The first `length` characters of `text`, marked as cut — never between a surrogate pair's halves. */
function cut(text, length) {
  const code = text.charCodeAt(length - 1);
  return `${text.slice(0, code >= 0xd800 && code <= 0xdbff ? length - 1 : length)}\n… (truncated)`;
}

/**
 * The navbar's links for a host running `version`: the defaults, with whatever the host changes.
 * A custom build of it (`build`, the id its Vite config names: `@text-to-cad/ui/build-id`) runs
 * `0.7.15-dev.<build>`, which the app menu shows and a new issue names; its release notes are still
 * those of the release it was built on.
 *
 * @param {object} options
 * @param {string} options.version The version this host runs.
 * @param {string} [options.build] The id of a custom build of it; "" (the release's own build) for none.
 * @param {string} [options.x]
 * @param {string} [options.github]
 * @param {string} [options.discord]
 * @param {string} [options.issues] Where a new issue is opened; "" offers none.
 * @param {string} [options.release] This version's release notes; by default its tag on `github`.
 * @param {(url: string) => Promise<void>} [options.open]
 */
export function viewerLinks({ version, build = "", x = TEXT_TO_CAD_LINKS.x, github = TEXT_TO_CAD_LINKS.github, discord = TEXT_TO_CAD_LINKS.discord,
  issues = TEXT_TO_CAD_LINKS.issues, release, open } = {}) {
  const bare = releaseVersion(version);
  const custom = String(build ?? "").trim();
  return {
    version: bare && custom ? `${bare}-dev.${custom}` : bare, x, github, discord, issues,
    release: release || releaseNotesUrl(github, bare),
    ...(open ? { open } : {})
  };
}

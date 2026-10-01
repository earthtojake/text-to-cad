/**
 * What the navbar's right end links to, in every app: the running version (its release notes and
 * how to update), the source and the community. `@text-to-cad/ui/links` — pure, with no imports,
 * so a host's own build configuration and its unit tests read the same defaults the navbar draws.
 *
 * A host supplies the version it runs and hands `viewerLinks(...)` to its `ViewerHost.links`. It
 * may point the links elsewhere (the web reads its build's environment), say what it found when
 * it checked for a newer release (`latest`), and say how a link is followed (`open`, for a page
 * in a frame that cannot open one itself). Nothing here fetches or navigates.
 */

export const TEXT_TO_CAD_LINKS = Object.freeze({
  x: "https://x.com/earthtojake",
  github: "https://github.com/earthtojake/text-to-cad",
  discord: "https://discord.gg/5FGB9DwJYU",
  install: Object.freeze({
    // `add` rather than `update`: both refresh what is installed, but only `add` picks up a skill
    // that is NEW in a release, because `update` walks the lockfile. Skills only: the skill text
    // tells the agent when and how to install or upgrade cadgen.
    command: "npx skills add earthtojake/text-to-cad",
    // The same update, handed to an agent instead of run in a terminal: one short line, read at a
    // glance in a menu and pasted into a chat where the agent already knows the rest of the job.
    prompt: "Update the text-to-cad skills with `npx skills add earthtojake/text-to-cad`."
  })
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

/**
 * The navbar's links for a host running `version`: the defaults, with whatever the host changes.
 *
 * @param {object} options
 * @param {string} options.version The version this host runs.
 * @param {string} [options.x]
 * @param {string} [options.github]
 * @param {string} [options.discord]
 * @param {string} [options.release] This version's release notes; by default its tag on `github`.
 * @param {{ command?: string, prompt?: string, message?: string }} [options.install]
 *   How this host updates, in place of the skills' update: see `ViewerLinks.install`.
 * @param {{ version: string, url: string, newer: boolean } | null} [options.latest]
 *   The newest release, for a host that checked, and whether it is newer than `version`.
 * @param {(url: string) => Promise<void>} [options.open]
 */
export function viewerLinks({ version, x = TEXT_TO_CAD_LINKS.x, github = TEXT_TO_CAD_LINKS.github, discord = TEXT_TO_CAD_LINKS.discord,
  release, install = TEXT_TO_CAD_LINKS.install, latest = null, open } = {}) {
  const bare = releaseVersion(version);
  return {
    version: bare, x, github, discord, install, latest,
    release: release || releaseNotesUrl(github, bare),
    ...(open ? { open } : {})
  };
}

import { TEXT_TO_CAD_LINKS, releaseVersion } from "@text-to-cad/ui/links";

// The links every app's navbar draws, by default (`@text-to-cad/ui/links`); this build may point
// GitHub and Discord elsewhere (`VIEWER_GITHUB_URL`, `VIEWER_DISCORD_URL`).
export const DEFAULT_VIEWER_GITHUB_URL = TEXT_TO_CAD_LINKS.github;
export const DEFAULT_VIEWER_DISCORD_URL = TEXT_TO_CAD_LINKS.discord;

export function normalizeViewerGithubUrl(value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  return normalizeHttpUrlCandidate(value) || normalizeHttpUrlCandidate(fallback);
}

export function normalizeViewerDiscordUrl(value = "", fallback = DEFAULT_VIEWER_DISCORD_URL) {
  return normalizeHttpUrlCandidate(value) || normalizeHttpUrlCandidate(fallback);
}

export function viewerGithubRepositoryUrl(value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  const normalized = normalizeViewerGithubUrl(value, fallback);
  if (!normalized) {
    return "";
  }
  try {
    const url = new URL(normalized);
    if (url.hostname.toLowerCase() !== "github.com") {
      return normalized.replace(/\/+$/, "");
    }
    const [, owner = "", repo = ""] = url.pathname.split("/");
    if (!owner || !repo) {
      return normalized.replace(/\/+$/, "");
    }
    return new URL(`/${owner}/${repo}`, url.origin).href.replace(/\/+$/, "");
  } catch {
    return "";
  }
}

/** A release VERSION as displayed and compared: a GitHub `tag_name` (`v0.5.0`, or the bare
 * `0.4.28` releases before 0.5.0 used) or a `refs/tags/...` ref, with the tag dressing removed.
 * The one place the `v` is stripped (`@text-to-cad/ui/links`); everything downstream sees bare versions. */
export const normalizeViewerReleaseVersion = releaseVersion;

/** The tag a release VERSION is published under: `v<version>` from 0.5.0 on. */
export function viewerReleaseTagName(version = "") {
  const normalizedVersion = normalizeViewerReleaseVersion(version);
  return normalizedVersion ? `v${normalizedVersion}` : "";
}

export function viewerGithubReleaseUrl(version = "", value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  const tagName = viewerReleaseTagName(version);
  const repositoryUrl = viewerGithubRepositoryUrl(value, fallback);
  if (!tagName || !repositoryUrl) {
    return "";
  }
  return `${repositoryUrl}/releases/tag/${encodeURIComponent(tagName)}`;
}

/** Where Feedback and Report Issue open a new issue: `issues/new` on this build's repository. */
export function viewerGithubIssueUrl(value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  const repositoryUrl = viewerGithubRepositoryUrl(value, fallback);
  return repositoryUrl ? `${repositoryUrl}/issues/new` : "";
}

function normalizeHttpUrlCandidate(value = "") {
  const rawValue = String(value ?? "").trim();
  if (!rawValue) {
    return "";
  }
  const urlValue = /^[a-z][a-z\d+.-]*:\/\//i.test(rawValue)
    ? rawValue
    : `https://${rawValue.replace(/^\/+/, "")}`;

  try {
    const url = new URL(urlValue);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

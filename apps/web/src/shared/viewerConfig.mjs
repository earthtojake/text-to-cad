import { TEXT_TO_CAD_LINKS, releaseVersion } from "@text-to-cad/ui/links";

// The links every app's navbar draws, by default (`@text-to-cad/ui/links`); this build may point
// GitHub and Discord elsewhere (`VIEWER_GITHUB_URL`, `VIEWER_DISCORD_URL`).
export const DEFAULT_VIEWER_GITHUB_URL = TEXT_TO_CAD_LINKS.github;
export const DEFAULT_VIEWER_DISCORD_URL = TEXT_TO_CAD_LINKS.discord;
export const DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND = TEXT_TO_CAD_LINKS.install.command;
export const DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT = TEXT_TO_CAD_LINKS.install.prompt;

export function normalizeViewerDefaultFile(value = "") {
  const rawValue = String(value ?? "").trim();
  return rawValue.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
}

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

export function viewerGithubLatestReleaseUrl(value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  const repositoryUrl = viewerGithubRepositoryUrl(value, fallback);
  if (!repositoryUrl) {
    return "";
  }
  return `${repositoryUrl}/releases/latest`;
}

export function viewerGithubLatestReleaseApiUrl(value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  const repositoryUrl = viewerGithubRepositoryUrl(value, fallback);
  if (!repositoryUrl) {
    return "";
  }

  try {
    const url = new URL(repositoryUrl);
    if (url.hostname.toLowerCase() !== "github.com") {
      return "";
    }
    const [, rawOwner = "", rawRepo = ""] = url.pathname.split("/");
    const owner = decodeURIComponent(rawOwner);
    const repo = decodeURIComponent(rawRepo);
    if (!owner || !repo) {
      return "";
    }
    return `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/releases/latest`;
  } catch {
    return "";
  }
}

export function isViewerReleaseNewer(currentVersion = "", candidateVersion = "") {
  const current = parseViewerReleaseVersion(currentVersion);
  const candidate = parseViewerReleaseVersion(candidateVersion);
  return Boolean(current && candidate && compareParsedViewerReleaseVersions(candidate, current) > 0);
}

export function isViewerReleaseMajorMinorNewer(currentVersion = "", candidateVersion = "") {
  const current = parseViewerReleaseVersion(currentVersion);
  const candidate = parseViewerReleaseVersion(candidateVersion);
  if (!current || !candidate || compareParsedViewerReleaseVersions(candidate, current) <= 0) {
    return false;
  }
  return candidate.parts[0] > current.parts[0] || candidate.parts[1] > current.parts[1];
}

/** Whether a newer release is worth PROMPTING about, rather than merely noting.
 *
 * Two thresholds exist because the top bar has two registers: any newer release reveals the
 * latest version quietly, while this one turns the version chip into an "Update" button.
 *
 * That prompt used to require a MAJOR or MINOR release, on the reasoning that a patch is not
 * worth interrupting anyone for. It is, at the current cadence: 0.4.7 through 0.4.10 shipped
 * inside three days and carried the Windows path fix, the SMB rename retry, the drawing rules
 * and the multi-bend fold -- fixes a user hitting those bugs has no way to learn about from a
 * quiet version number. So patches prompt too, for now.
 *
 * This is the one place that policy lives: restoring the old behaviour means calling
 * `isViewerReleaseMajorMinorNewer` here instead, and nothing else changes.
 */
export function isViewerReleaseUpdateSuggested(currentVersion = "", candidateVersion = "") {
  return isViewerReleaseNewer(currentVersion, candidateVersion);
}

export function normalizeViewerSkillsInstallCommand(
  value = "",
  fallback = DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
) {
  const command = cleanInstallCommandCandidate(value);
  // Both spellings: `install` is an alias for `add`, and release bodies may use either. No
  // token may carry a shell operator (`&&`, `;`, `|`, backticks, `$`): this string is put in
  // front of the user to run, so a release body must not be able to chain anything onto it.
  if (/^npx\s+skills\s+(?:install|add)(?:\s+[^\s;&|`$]+)+$/iu.test(command)) {
    return command;
  }
  return String(fallback || "").trim();
}

export function viewerSkillsInstallCommandFromText(
  value = "",
  fallback = DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
) {
  const source = String(value || "");
  const candidates = [
    ...Array.from(source.matchAll(/`([^`\r\n]*\bnpx\s+skills\s+(?:install|add)\b[^`\r\n]*)`/giu), (match) => match[1]),
    ...Array.from(source.matchAll(/(?:^|\n)\s*([^\r\n]*\bnpx\s+skills\s+(?:install|add)\b[^\r\n]*)/giu), (match) => match[1])
  ];

  for (const candidate of candidates) {
    const command = normalizeViewerSkillsInstallCommand(candidate, "");
    if (command) {
      return command;
    }
  }

  return String(fallback || "").trim();
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

function cleanInstallCommandCandidate(value = "") {
  return String(value || "")
    .trim()
    .replace(/^`+|`+$/g, "")
    .replace(/^\s*(?:\$|>)\s*/u, "")
    .replace(/\s+/gu, " ");
}

function parseViewerReleaseVersion(value = "") {
  const rawValue = normalizeViewerReleaseVersion(value);
  if (!rawValue) {
    return null;
  }

  const withoutBuild = rawValue.split("+")[0];
  const [core = "", ...prereleaseParts] = withoutBuild.split("-");
  const match = core.match(/^(\d+)(?:\.(\d+))?(?:\.(\d+))?$/u);
  if (!match) {
    return null;
  }

  return {
    parts: [
      Number(match[1]),
      Number(match[2] || 0),
      Number(match[3] || 0)
    ],
    prerelease: prereleaseParts.join("-").split(".").filter(Boolean)
  };
}

function compareParsedViewerReleaseVersions(left, right) {
  for (let index = 0; index < 3; index += 1) {
    const difference = left.parts[index] - right.parts[index];
    if (difference !== 0) {
      return difference;
    }
  }

  return compareViewerPrereleaseIdentifiers(left.prerelease, right.prerelease);
}

function compareViewerPrereleaseIdentifiers(left, right) {
  if (!left.length && !right.length) {
    return 0;
  }
  if (!left.length) {
    return 1;
  }
  if (!right.length) {
    return -1;
  }

  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftValue = left[index];
    const rightValue = right[index];
    if (leftValue === undefined) {
      return -1;
    }
    if (rightValue === undefined) {
      return 1;
    }
    if (leftValue === rightValue) {
      continue;
    }

    const leftNumeric = /^\d+$/u.test(leftValue);
    const rightNumeric = /^\d+$/u.test(rightValue);
    if (leftNumeric && rightNumeric) {
      return Number(leftValue) - Number(rightValue);
    }
    if (leftNumeric) {
      return -1;
    }
    if (rightNumeric) {
      return 1;
    }
    return leftValue.localeCompare(rightValue);
  }

  return 0;
}

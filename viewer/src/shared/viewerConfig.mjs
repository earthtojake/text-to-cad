export const DEFAULT_VIEWER_GITHUB_URL = "https://github.com/earthtojake/text-to-cad";
export const DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND = "npx skills install earthtojake/text-to-cad";

export function normalizeViewerDefaultFile(value = "") {
  const rawValue = String(value ?? "").trim();
  return rawValue.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
}

export function normalizeViewerGithubUrl(value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  return normalizeViewerGithubUrlCandidate(value) || normalizeViewerGithubUrlCandidate(fallback);
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

export function viewerGithubReleaseUrl(version = "", value = "", fallback = DEFAULT_VIEWER_GITHUB_URL) {
  const normalizedVersion = String(version || "").trim();
  const repositoryUrl = viewerGithubRepositoryUrl(value, fallback);
  if (!normalizedVersion || !repositoryUrl) {
    return "";
  }
  return `${repositoryUrl}/releases/tag/${encodeURIComponent(normalizedVersion)}`;
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

export function normalizeViewerSkillsInstallCommand(
  value = "",
  fallback = DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
) {
  const command = cleanInstallCommandCandidate(value);
  if (/^npx\s+skills\s+install(?:\s+\S+)+$/iu.test(command)) {
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
    ...Array.from(source.matchAll(/`([^`\r\n]*\bnpx\s+skills\s+install\b[^`\r\n]*)`/giu), (match) => match[1]),
    ...Array.from(source.matchAll(/(?:^|\n)\s*([^\r\n]*\bnpx\s+skills\s+install\b[^\r\n]*)/giu), (match) => match[1])
  ];

  for (const candidate of candidates) {
    const command = normalizeViewerSkillsInstallCommand(candidate, "");
    if (command) {
      return command;
    }
  }

  return String(fallback || "").trim();
}

function normalizeViewerGithubUrlCandidate(value = "") {
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
  const rawValue = String(value ?? "")
    .trim()
    .replace(/^refs\/tags\//i, "")
    .replace(/^v/i, "");
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

/**
 * The navbar's links as this Viewer builds them (`ViewerHost.links`): its version, where GitHub
 * and Discord are for this build, and — the one thing only the web does — whether a newer release
 * is out, from GitHub's latest-release API, cached for a few hours. The navbar draws them the same
 * in every app (`@text-to-cad/ui/links`); release polling never enters shared UI.
 */
import { useEffect, useMemo, useState } from "react";
import { viewerLinks } from "@text-to-cad/ui/links";

import {
  DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND,
  DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT,
  isViewerReleaseUpdateSuggested,
  normalizeViewerDiscordUrl,
  normalizeViewerGithubUrl,
  normalizeViewerReleaseVersion,
  viewerGithubLatestReleaseApiUrl,
  viewerGithubLatestReleaseUrl,
  viewerGithubReleaseUrl,
  viewerSkillsInstallCommandFromText
} from "../shared/viewerConfig.mjs";
import viewerPackage from "../../package.json";

const latestReleaseCacheKeyPrefix = "cad-viewer:latest-release:v1:";
const latestReleaseCacheTtlMs = 6 * 60 * 60 * 1000;

function latestReleaseCacheKey(apiUrl) {
  return `${latestReleaseCacheKeyPrefix}${apiUrl}`;
}

function readLatestReleaseCache(apiUrl, now = Date.now()) {
  if (!apiUrl || typeof window === "undefined" || !window.localStorage) return null;
  try {
    const value = JSON.parse(window.localStorage.getItem(latestReleaseCacheKey(apiUrl)) || "null");
    const latestVersion = String(value?.latestVersion || "").trim();
    if (!latestVersion || Number(value?.expiresAt || 0) <= now) return null;
    return { latestVersion, releaseUrl: String(value?.releaseUrl || "").trim(), installCommand: String(value?.installCommand || "").trim() };
  } catch {
    return null;
  }
}

function writeLatestReleaseCache(apiUrl, release, now = Date.now()) {
  if (!apiUrl || typeof window === "undefined" || !window.localStorage || !release?.latestVersion) return;
  try {
    window.localStorage.setItem(latestReleaseCacheKey(apiUrl), JSON.stringify({ ...release, expiresAt: now + latestReleaseCacheTtlMs }));
  } catch {
    // Local storage availability is browser-policy dependent; the release check is optional.
  }
}

// `tag_name` is `v0.5.0`; everything downstream wants `0.5.0`. Normalized ONCE, here.
function latestReleaseFromPayload(payload, fallbackReleaseUrl = "") {
  const latestVersion = normalizeViewerReleaseVersion(payload?.tag_name);
  if (!latestVersion) return null;
  return {
    latestVersion,
    releaseUrl: String(payload?.html_url || fallbackReleaseUrl || "").trim(),
    installCommand: viewerSkillsInstallCommandFromText(payload?.body, DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND)
  };
}

/** The newest release, when this build can ask GitHub: `{ latestVersion, releaseUrl, installCommand }` or null. */
function useLatestRelease({ latestReleaseApiUrl, latestReleaseUrl, mockLatestVersion, mockLatestReleaseUrl }) {
  const [release, setRelease] = useState(null);
  useEffect(() => {
    if (mockLatestVersion) {
      setRelease({ latestVersion: mockLatestVersion, releaseUrl: mockLatestReleaseUrl || latestReleaseUrl, installCommand: DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND });
      return undefined;
    }
    if (!latestReleaseApiUrl || typeof fetch !== "function") { setRelease(null); return undefined; }
    const cached = readLatestReleaseCache(latestReleaseApiUrl);
    if (cached) { setRelease(cached); return undefined; }
    setRelease(null);
    const controller = new AbortController();
    fetch(latestReleaseApiUrl, { signal: controller.signal, headers: { Accept: "application/vnd.github+json" } })
      .then((response) => {
        if (!response.ok) throw new Error(`GitHub latest release check failed with ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (controller.signal.aborted) return;
        const latest = latestReleaseFromPayload(payload, latestReleaseUrl);
        if (latest) writeLatestReleaseCache(latestReleaseApiUrl, latest);
        setRelease(latest);
      })
      .catch(() => { /* the check is optional: the version stays as it is */ });
    return () => controller.abort();
  }, [latestReleaseApiUrl, latestReleaseUrl, mockLatestVersion, mockLatestReleaseUrl]);
  return release;
}

/** This Viewer's `ViewerHost.links`: the version it runs, X, its build's GitHub and Discord, and what GitHub says is newest. */
export function useViewerLinks() {
  const version = normalizeViewerReleaseVersion(viewerPackage.version);
  const github = normalizeViewerGithubUrl(import.meta.env?.VIEWER_GITHUB_URL);
  const discord = normalizeViewerDiscordUrl(import.meta.env?.VIEWER_DISCORD_URL);
  const latestReleaseUrl = viewerGithubLatestReleaseUrl(github);
  const mockLatestVersion = import.meta.env?.DEV ? String(import.meta.env?.VIEWER_MOCK_LATEST_VERSION || "").trim() : "";
  const release = useLatestRelease({
    latestReleaseApiUrl: viewerGithubLatestReleaseApiUrl(github), latestReleaseUrl, mockLatestVersion,
    mockLatestReleaseUrl: mockLatestVersion ? viewerGithubReleaseUrl(mockLatestVersion, github) : ""
  });
  return useMemo(() => viewerLinks({
    version, github, discord, release: viewerGithubReleaseUrl(version, github),
    install: { command: release?.installCommand || DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND, prompt: DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT },
    latest: release ? { version: release.latestVersion, url: release.releaseUrl, newer: isViewerReleaseUpdateSuggested(version, release.latestVersion) } : null
  }), [version, github, discord, release]);
}

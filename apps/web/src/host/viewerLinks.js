/**
 * The navbar's links as this Viewer builds them (`ViewerHost.links`): its version, and where GitHub
 * and Discord are for this build. The navbar draws them the same in every app
 * (`@text-to-cad/ui/links`). A newer release is cadgen's to say, through the update card
 * (`/__cad/version`).
 */
import { useMemo } from "react";
import { viewerLinks } from "@text-to-cad/ui/links";

import {
  normalizeViewerDiscordUrl,
  normalizeViewerGithubUrl,
  viewerGithubIssueUrl,
  viewerGithubReleaseUrl
} from "../shared/viewerConfig.mjs";
import viewerPackage from "../../package.json";

// Which build this is, where it is not the release's own: vite.config.mjs names it
// (`@text-to-cad/ui/build-id`), and the version then reads `0.7.15-dev.<build>`.
const BUILD = typeof __TEXT_TO_CAD_BUILD__ === "string" ? __TEXT_TO_CAD_BUILD__ : "";

/** This Viewer's `ViewerHost.links`: the version it runs, X, its build's GitHub (and new issues there) and Discord. */
export function useViewerLinks() {
  const version = viewerPackage.version;
  const github = normalizeViewerGithubUrl(import.meta.env?.VIEWER_GITHUB_URL);
  const discord = normalizeViewerDiscordUrl(import.meta.env?.VIEWER_DISCORD_URL);
  return useMemo(() => viewerLinks({
    version, build: BUILD, github, discord, issues: viewerGithubIssueUrl(github), release: viewerGithubReleaseUrl(version, github)
  }), [version, github, discord]);
}

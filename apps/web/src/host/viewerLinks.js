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

/** This Viewer's `ViewerHost.links`: the version it runs, X, its build's GitHub (and new issues there) and Discord. */
export function useViewerLinks() {
  const version = viewerPackage.version;
  const github = normalizeViewerGithubUrl(import.meta.env?.VIEWER_GITHUB_URL);
  const discord = normalizeViewerDiscordUrl(import.meta.env?.VIEWER_DISCORD_URL);
  return useMemo(() => viewerLinks({
    version, github, discord, issues: viewerGithubIssueUrl(github), release: viewerGithubReleaseUrl(version, github)
  }), [version, github, discord]);
}

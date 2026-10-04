import assert from "node:assert/strict";
import test from "node:test";
import { TEXT_TO_CAD_LINKS } from "@text-to-cad/ui/links";

import {
  DEFAULT_VIEWER_DISCORD_URL,
  DEFAULT_VIEWER_GITHUB_URL,
  normalizeViewerReleaseVersion,
  viewerReleaseTagName,
  normalizeViewerDiscordUrl,
  normalizeViewerGithubUrl,
  viewerGithubIssueUrl,
  viewerGithubReleaseUrl,
  viewerGithubRepositoryUrl
} from "./viewerConfig.mjs";

test("normalizeViewerGithubUrl defaults to the CAD Viewer repository link", () => {
  assert.equal(normalizeViewerGithubUrl(""), DEFAULT_VIEWER_GITHUB_URL);
});

test("normalizeViewerGithubUrl accepts configured GitHub URLs", () => {
  assert.equal(
    normalizeViewerGithubUrl("github.com/example/repo"),
    "https://github.com/example/repo"
  );
  assert.equal(
    normalizeViewerGithubUrl("https://github.com/example/repo/tree/main"),
    "https://github.com/example/repo/tree/main"
  );
});

test("normalizeViewerGithubUrl falls back to a configured default", () => {
  assert.equal(
    normalizeViewerGithubUrl("", "github.com/example/default"),
    "https://github.com/example/default"
  );
});

test("normalizeViewerDiscordUrl defaults to the text-to-cad Discord invite", () => {
  assert.equal(normalizeViewerDiscordUrl(""), DEFAULT_VIEWER_DISCORD_URL);
});

test("normalizeViewerDiscordUrl accepts configured invite URLs", () => {
  assert.equal(
    normalizeViewerDiscordUrl("discord.gg/example"),
    "https://discord.gg/example"
  );
  assert.equal(
    normalizeViewerDiscordUrl("https://example.com/community"),
    "https://example.com/community"
  );
});

test("viewerGithubRepositoryUrl trims GitHub branch paths to the repository", () => {
  assert.equal(
    viewerGithubRepositoryUrl("https://github.com/example/repo/tree/main"),
    "https://github.com/example/repo"
  );
});

test("viewerGithubReleaseUrl links to the v-prefixed release tag", () => {
  // Releases are tagged `v<version>` from 0.5.0 on; the running version is bare.
  assert.equal(
    viewerGithubReleaseUrl("0.5.0", "github.com/example/repo/tree/main"),
    "https://github.com/example/repo/releases/tag/v0.5.0"
  );
  // An already-prefixed value is not doubled.
  assert.equal(
    viewerGithubReleaseUrl("v0.5.0", "github.com/example/repo"),
    "https://github.com/example/repo/releases/tag/v0.5.0"
  );
  assert.equal(viewerGithubReleaseUrl("", "github.com/example/repo"), "");
});

test("viewerGithubIssueUrl opens a new issue on the build's repository, the shared default unless it names another", () => {
  assert.equal(viewerGithubIssueUrl(""), TEXT_TO_CAD_LINKS.issues);
  assert.equal(viewerGithubIssueUrl("github.com/example/repo/tree/main"), "https://github.com/example/repo/issues/new");
});

test("normalizeViewerReleaseVersion strips the tag dressing once, for display and comparison", () => {
  assert.equal(normalizeViewerReleaseVersion("v0.5.0"), "0.5.0");
  assert.equal(normalizeViewerReleaseVersion("0.4.28"), "0.4.28");
  assert.equal(normalizeViewerReleaseVersion("refs/tags/v0.5.0"), "0.5.0");
  assert.equal(normalizeViewerReleaseVersion(" V0.5.0 "), "0.5.0");
  // Only a `v` in front of a digit is tag dressing.
  assert.equal(normalizeViewerReleaseVersion("vnext"), "vnext");
  assert.equal(viewerReleaseTagName("0.5.0"), "v0.5.0");
  assert.equal(viewerReleaseTagName("v0.5.0"), "v0.5.0");
  assert.equal(viewerReleaseTagName(""), "");
});

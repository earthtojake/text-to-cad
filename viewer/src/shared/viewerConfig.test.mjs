import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_VIEWER_GITHUB_URL,
  DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND,
  isViewerReleaseMajorMinorNewer,
  isViewerReleaseNewer,
  normalizeViewerDefaultFile,
  normalizeViewerGithubUrl,
  normalizeViewerSkillsInstallCommand,
  viewerGithubLatestReleaseApiUrl,
  viewerGithubLatestReleaseUrl,
  viewerGithubReleaseUrl,
  viewerGithubRepositoryUrl,
  viewerSkillsInstallCommandFromText
} from "./viewerConfig.mjs";

test("normalizeViewerDefaultFile keeps scan-relative file paths", () => {
  assert.equal(normalizeViewerDefaultFile("/STEP/sample_part.step/"), "STEP/sample_part.step");
  assert.equal(normalizeViewerDefaultFile("STEP\\sample_part.step"), "STEP/sample_part.step");
});

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

test("viewerGithubRepositoryUrl trims GitHub branch paths to the repository", () => {
  assert.equal(
    viewerGithubRepositoryUrl("https://github.com/example/repo/tree/main"),
    "https://github.com/example/repo"
  );
});

test("viewerGithubReleaseUrl links to the requested release tag", () => {
  assert.equal(
    viewerGithubReleaseUrl("0.1.10", "github.com/example/repo/tree/main"),
    "https://github.com/example/repo/releases/tag/0.1.10"
  );
});

test("viewerGithubLatestReleaseUrl links to the latest release page", () => {
  assert.equal(
    viewerGithubLatestReleaseUrl("github.com/example/repo/tree/main"),
    "https://github.com/example/repo/releases/latest"
  );
});

test("viewerGithubLatestReleaseApiUrl links to the GitHub latest release API", () => {
  assert.equal(
    viewerGithubLatestReleaseApiUrl("github.com/example/repo/tree/main"),
    "https://api.github.com/repos/example/repo/releases/latest"
  );
  assert.equal(viewerGithubLatestReleaseApiUrl("https://example.com/example/repo"), "");
});

test("isViewerReleaseNewer compares release versions", () => {
  assert.equal(isViewerReleaseNewer("0.1.16", "0.1.17"), true);
  assert.equal(isViewerReleaseNewer("0.1.16", "v0.1.17"), true);
  assert.equal(isViewerReleaseNewer("0.1.16", "0.1.16"), false);
  assert.equal(isViewerReleaseNewer("0.1.16", "0.1.15"), false);
  assert.equal(isViewerReleaseNewer("0.2.0-beta.1", "0.2.0"), true);
  assert.equal(isViewerReleaseNewer("0.2.0", "0.2.0-beta.1"), false);
  assert.equal(isViewerReleaseNewer("0.1.16", "latest"), false);
});

test("isViewerReleaseMajorMinorNewer ignores patch-only releases", () => {
  assert.equal(isViewerReleaseMajorMinorNewer("0.1.16", "0.1.17"), false);
  assert.equal(isViewerReleaseMajorMinorNewer("0.1.16", "0.2.0"), true);
  assert.equal(isViewerReleaseMajorMinorNewer("0.1.16", "1.0.0"), true);
  assert.equal(isViewerReleaseMajorMinorNewer("0.2.0-beta.1", "0.2.0"), false);
  assert.equal(isViewerReleaseMajorMinorNewer("0.2.0", "0.2.1"), false);
  assert.equal(isViewerReleaseMajorMinorNewer("0.2.0", "0.1.99"), false);
});

test("normalizeViewerSkillsInstallCommand accepts only skills install commands", () => {
  assert.equal(
    normalizeViewerSkillsInstallCommand("$ npx   skills install   earthtojake/text-to-cad"),
    DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
  );
  assert.equal(
    normalizeViewerSkillsInstallCommand("npx skills install example/repo --channel beta"),
    "npx skills install example/repo --channel beta"
  );
  assert.equal(
    normalizeViewerSkillsInstallCommand("npm install example/repo"),
    DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
  );
});

test("viewerSkillsInstallCommandFromText extracts release-body install commands", () => {
  assert.equal(
    viewerSkillsInstallCommandFromText([
      "Install:",
      "```bash",
      "npx skills install example/repo",
      "```"
    ].join("\n")),
    "npx skills install example/repo"
  );
  assert.equal(
    viewerSkillsInstallCommandFromText("No command here."),
    DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
  );
});

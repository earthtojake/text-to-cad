import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_VIEWER_DISCORD_URL,
  DEFAULT_VIEWER_GITHUB_URL,
  DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND,
  DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT,
  isViewerReleaseMajorMinorNewer,
  isViewerReleaseNewer,
  isViewerReleaseUpdateSuggested,
  normalizeViewerDefaultFile,
  normalizeViewerDiscordUrl,
  normalizeViewerGithubUrl,
  normalizeViewerSkillsInstallCommand,
  normalizeViewerSkillsUpdatePrompt,
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

test("a patch release is worth prompting about, at this cadence", () => {
  // The prompt turns the version chip into an "Update" button. It used to require a major or
  // minor release; patches now qualify too, because that is where the fixes have been shipping.
  assert.equal(isViewerReleaseUpdateSuggested("0.4.9", "0.4.10"), true);
  assert.equal(isViewerReleaseUpdateSuggested("0.4.10", "0.5.0"), true);
  assert.equal(isViewerReleaseUpdateSuggested("0.4.10", "1.0.0"), true);
  // Same version, older version, and an unparseable tag must never prompt.
  assert.equal(isViewerReleaseUpdateSuggested("0.4.10", "0.4.10"), false);
  assert.equal(isViewerReleaseUpdateSuggested("0.4.10", "0.4.9"), false);
  assert.equal(isViewerReleaseUpdateSuggested("0.4.10", "latest"), false);
  // A prerelease of the version you already run is not an upgrade.
  assert.equal(isViewerReleaseUpdateSuggested("0.2.0", "0.2.0-beta.1"), false);
  // The narrower rule still exists, and still ignores patches -- restoring it is a one-line
  // change inside the policy function.
  assert.equal(isViewerReleaseMajorMinorNewer("0.4.9", "0.4.10"), false);
});

test("normalizeViewerSkillsInstallCommand accepts skills add/install and nothing else", () => {
  // A shell prompt and padding are stripped, so a command pasted out of a release body works.
  assert.equal(
    normalizeViewerSkillsInstallCommand("$ npx   skills add   earthtojake/text-to-cad"),
    "npx skills add earthtojake/text-to-cad"
  );
  // `install` is an undocumented alias for `add`, and older release bodies use it, so it stays
  // acceptable rather than being rewritten into the fallback.
  assert.equal(
    normalizeViewerSkillsInstallCommand("npx skills install earthtojake/text-to-cad"),
    "npx skills install earthtojake/text-to-cad"
  );
  assert.equal(
    normalizeViewerSkillsInstallCommand("npx skills add example/repo --channel beta"),
    "npx skills add example/repo --channel beta"
  );
  // Anything that is not a skills add/install falls back: this string is put in front of the
  // user to run, so an unrecognised command must never pass through.
  assert.equal(
    normalizeViewerSkillsInstallCommand("npm install example/repo"),
    DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
  );
  assert.equal(
    normalizeViewerSkillsInstallCommand("npx skills remove cad"),
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

test("the agent update prompt names the command, in one short line", () => {
  assert.match(DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT, /npx skills add earthtojake\/text-to-cad/u);
  // `add`, not `update`: only `add` picks up a skill that is new in a release.
  assert.doesNotMatch(DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT, /npx skills update/u);
  // It is read at a glance in a popover, so it stays one short line.
  assert.equal(DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT.split("\n").length, 1);
  assert.ok(DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT.length < 90);
});

test("normalizeViewerSkillsUpdatePrompt rejects a prompt with no command in it", () => {
  const custom = "Run `npx skills add earthtojake/text-to-cad` for me.";
  assert.equal(normalizeViewerSkillsUpdatePrompt(custom), custom);
  // The `install` spelling is an accepted alias, so an older prompt still passes through.
  const legacy = "Run `npx skills install earthtojake/text-to-cad`.";
  assert.equal(normalizeViewerSkillsUpdatePrompt(legacy), legacy);
  // Prose with no command leaves the agent guessing at a channel: fall back instead.
  assert.equal(
    normalizeViewerSkillsUpdatePrompt("Please update the skills."),
    DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT
  );
  assert.equal(normalizeViewerSkillsUpdatePrompt(""), DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT);
  assert.equal(normalizeViewerSkillsUpdatePrompt(null), DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT);
});

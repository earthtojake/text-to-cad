import assert from "node:assert/strict";
import test from "node:test";
import { TEXT_TO_CAD_LINKS, issueUrl, releaseNotesUrl, releaseVersion, viewerLinks } from "./links.js";

const ISSUES = TEXT_TO_CAD_LINKS.issues;
const read = (url) => new URL(url).searchParams;

test("a new issue opens with its title, its labels (comma-separated, none when there are none) and its body", () => {
  assert.equal(issueUrl(ISSUES, { title: "Feedback: ", labels: ["bug", "good first issue"], body: "b" }),
    `${ISSUES}?title=Feedback%3A+&labels=bug%2Cgood+first+issue&body=b`);
  for (const labels of [undefined, [], ["", " "]]) assert.equal(issueUrl(ISSUES, { title: "x", labels }), `${ISSUES}?title=x`);
  // A tracker that is already addressed with a query keeps it; none, no address.
  assert.equal(issueUrl("https://tracker.test/new?template=bug.md", { title: "x", labels: ["bug"] }), "https://tracker.test/new?template=bug.md&title=x&labels=bug");
  assert.equal(issueUrl("", { title: "x" }), "");
});

test("the title and the labels count against the cap and are never cut: Details give way first, then the body", () => {
  const issue = { title: "Issue: ", labels: ["bug"], about: { CAD: "0.7.5" } };
  const front = `${ISSUES}?title=Issue%3A+&labels=bug&body=`;
  const max = front.length + 300;
  const long = issueUrl(ISSUES, { ...issue, body: "b".repeat(40), details: "d".repeat(5000) }, max);
  assert.ok(long.startsWith(front) && long.length <= max && long.length > max - 30, `${long.length} of ${max}`);
  const body = read(long).get("body");
  assert.ok(body.startsWith(`${"b".repeat(40)}\n\n**Environment**\n\n- CAD: 0.7.5\n\n**Details**`), "the body whole");
  assert.ok(body.endsWith("\n… (truncated)\n```"), "the Details cut from their end");
  // No room for any Details: the body is cut instead, and they are gone.
  const squeezed = issueUrl(ISSUES, { ...issue, body: "b".repeat(5000), details: "d" }, max);
  assert.ok(squeezed.startsWith(front) && squeezed.length <= max);
  assert.ok(read(squeezed).get("body").endsWith("b\n… (truncated)") && !squeezed.includes("Details"));
  // The title and the labels alone past the cap: the bare address, never a cut title.
  assert.equal(issueUrl(ISSUES, { ...issue, title: "t".repeat(500) }, 100), ISSUES);
});

test("a version is shown bare, its tag dressing stripped once, and its notes are under its v-tag", () => {
  assert.deepEqual(["v0.5.0", "0.4.28", "refs/tags/v0.5.0", " V0.5.0 ", "vnext"].map(releaseVersion), ["0.5.0", "0.4.28", "0.5.0", "0.5.0", "vnext"]);
  assert.equal(releaseNotesUrl("https://github.com/example/repo/", "v0.5.0"), "https://github.com/example/repo/releases/tag/v0.5.0");
  assert.equal(releaseNotesUrl("https://github.com/example/repo", ""), "");
});

test("the release's own build runs its version; a custom build runs it with its id, and keeps the release's notes", () => {
  const notes = "https://github.com/earthtojake/text-to-cad/releases/tag/v0.7.15";
  const shown = (options) => { const links = viewerLinks(options); return [links.version, links.release]; };
  assert.deepEqual(shown({ version: "v0.7.15" }), ["0.7.15", notes]);
  assert.deepEqual(shown({ version: "0.7.15", build: "" }), ["0.7.15", notes]);
  assert.deepEqual(shown({ version: "0.7.15", build: "b80844940" }), ["0.7.15-dev.b80844940", notes]);
  assert.deepEqual(shown({ version: "0.7.15", build: "b80844940-dirty" }), ["0.7.15-dev.b80844940-dirty", notes]);
});

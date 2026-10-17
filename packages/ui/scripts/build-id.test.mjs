import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { RELEASE_ENV, buildId } from "./build-id.mjs";

// A checkout of its own, with one commit: nothing here reads this repository's.
function checkout() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "build-id-"));
  const git = (...args) => execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", ...args],
    { cwd: root, encoding: "utf8" }).trim();
  git("init", "-q");
  fs.writeFileSync(path.join(root, "VERSION"), "0.7.15\n");
  git("add", "VERSION");
  git("commit", "-q", "-m", "One commit");
  return { root, commit: git("rev-parse", "--short", "HEAD") };
}

test("the release's own build has no id; any other build is its checkout's commit, and says when it held changes", (t) => {
  const { root, commit } = checkout();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const id = (env) => buildId({ version: "0.7.15", env, cwd: root });
  assert.equal(id({ [RELEASE_ENV]: "0.7.15" }), "");
  // No marker, or one naming another version (a release's, left in a shell): a custom build.
  assert.equal(id({}), commit);
  assert.equal(id({ [RELEASE_ENV]: "0.7.14" }), commit);
  assert.equal(id({ [RELEASE_ENV]: "1" }), commit);
  assert.match(commit, /^[0-9a-f]{7,}$/u);
  // A file git does not track changes no build but through one it does.
  fs.writeFileSync(path.join(root, "notes.txt"), "draft\n");
  assert.equal(id({}), commit);
  // A change no commit holds.
  fs.writeFileSync(path.join(root, "VERSION"), "0.7.16\n");
  assert.equal(id({}), `${commit}-dirty`);
  assert.equal(id({ [RELEASE_ENV]: "0.7.15" }), "");
});

test("a custom build outside any checkout is named for when it was built", (t) => {
  const outside = fs.mkdtempSync(path.join(os.tmpdir(), "build-id-"));
  // git looks no further up than the temporary directory: it finds no checkout around this one.
  const ceiling = process.env.GIT_CEILING_DIRECTORIES;
  process.env.GIT_CEILING_DIRECTORIES = path.dirname(outside);
  t.after(() => {
    if (ceiling === undefined) delete process.env.GIT_CEILING_DIRECTORIES;
    else process.env.GIT_CEILING_DIRECTORIES = ceiling;
    fs.rmSync(outside, { recursive: true, force: true });
  });
  const now = new Date("2026-10-07T15:30:12.345Z");
  assert.equal(buildId({ version: "0.7.15", env: {}, cwd: outside, now }), "20261007153012");
  assert.equal(buildId({ version: "0.7.15", env: { [RELEASE_ENV]: "0.7.15" }, cwd: outside, now }), "");
});

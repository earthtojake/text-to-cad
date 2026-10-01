/**
 * `.github/workflows/release-publish.yml`, read as data: the release is the one
 * thing that cannot be run to see whether it works, so what it hands each
 * build is checked against what the build reads.
 */
import { execFileSync, spawnSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..", "..");
// js-yaml is not a direct dependency: it is in the tree because electron-updater needs it.
const require = createRequire(import.meta.url);
const { load } = require("js-yaml") as { load: (text: string) => Workflow };

interface Step {
  name?: string;
  env?: Record<string, string>;
  run?: string;
}
interface Workflow {
  jobs: Record<string, { if?: string; steps: Step[]; strategy?: { matrix: { include: { name: string }[] } } }>;
}

const workflow = load(readFileSync(path.join(repo, ".github", "workflows", "release-publish.yml"), "utf8"));

function job(name: string) {
  const found = workflow.jobs[name];
  if (found === undefined) throw new Error(`release-publish.yml has no ${name} job`);
  return found;
}

it("hands every signing secret to the leg whose os reads it, and to no other", async () => {
  const { SIGNING_SECRETS } = await import("../../../scripts/package.mjs");
  const legs: Record<string, string> = { mac: "macOS", win: "Windows" };
  const desktop = job("desktop");
  const env = desktop.steps.find((step) => step.name === "Build and package")?.env ?? {};
  // `${{ matrix.name == 'X' && secrets.NAME || '' }}`, evaluated for one leg.
  const handed = (leg: string, name: string) => {
    const expression = /^\$\{\{ matrix\.name == '(\w+)' && secrets\.(\w+) \|\| '' \}\}$/.exec(env[name] ?? "");
    return expression !== null && expression[2] === name && expression[1] === leg;
  };
  const missing: string[] = [];
  for (const { name: leg } of desktop.strategy?.matrix.include ?? []) {
    for (const [os, names] of Object.entries(SIGNING_SECRETS as Record<string, string[]>)) {
      for (const name of names) {
        if (handed(leg, name) !== (legs[os] === leg)) missing.push(`${leg}: ${name}`);
      }
    }
  }
  expect(missing, "legs whose signing secrets are mapped wrongly").toEqual([]);
});

describe("the release gate", () => {
  const gate = job("publish").steps.find((step) => step.name === "Evaluate release gate")?.run ?? "";

  /**
   * The gate's own script, run like CI runs it (`bash -eo pipefail`) in a
   * throwaway repository whose only release is the current version, tagged.
   * `stub` is the body of the fake `gh`; `tag` says whether the tag sits on
   * the commit being run or on an earlier one. Returns should_publish, or the
   * gate's exit status and stderr when it fails.
   */
  function runGate(stub: string, tag: "head" | "earlier" = "head"): { publish: string; status: number; stderr: string } {
    expect(gate.trim(), "extracted gate script").not.toBe("");
    const dir = mkdtempSync(path.join(tmpdir(), "release-gate-"));
    try {
      cpSync(path.join(repo, "scripts", "release"), path.join(dir, "scripts", "release"), { recursive: true });
      mkdirSync(path.join(dir, "skills"));
      mkdirSync(path.join(dir, "bin"));
      writeFileSync(path.join(dir, "VERSION"), "0.5.0\n");
      writeFileSync(path.join(dir, "bin", "gh"), `#!/bin/sh\n${stub}\n`, { mode: 0o755 });
      const git = (...args: string[]) => execFileSync("git", args, { cwd: dir, stdio: "pipe" });
      const commit = (message: string) =>
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", message);
      git("init", "-q");
      git("add", "-A");
      commit("release");
      if (tag === "earlier") {
        git("tag", "v0.5.0");
        commit("unrelated push");
      } else {
        git("tag", "v0.5.0");
      }
      const sha = git("rev-parse", "HEAD").toString().trim();
      const output = path.join(dir, "out");
      writeFileSync(output, "");
      const result = spawnSync("bash", ["--noprofile", "--norc", "-eo", "pipefail", "-c", gate], {
        cwd: dir,
        encoding: "utf8",
        env: {
          PATH: `${path.join(dir, "bin")}:${process.env.PATH}`,
          GITHUB_OUTPUT: output,
          GITHUB_REF: "refs/heads/main",
          GITHUB_REF_NAME: "main",
          GITHUB_SHA: sha,
          RUNNER_TEMP: dir,
          HOME: dir,
        },
      });
      const publish = /^should_publish=(\w+)$/m.exec(readFileSync(output, "utf8"))?.[1] ?? "";
      return { publish, status: result.status ?? -1, stderr: result.stderr };
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
  const draft = (isDraft: "true" | "false") => `echo ${isDraft}`;
  const notFound = 'echo "release not found" >&2; exit 1';

  it("resumes the tagged commit whose Release was never created or is still a draft", () => {
    expect(runGate(notFound).publish, "tag on HEAD, no Release").toBe("true");
    expect(runGate(draft("true")).publish, "tag on HEAD, draft Release").toBe("true");
  });

  it("does not rebuild a tagged version from a later commit", () => {
    expect(runGate(draft("true"), "earlier").publish, "tag on an earlier commit, draft Release").toBe("false");
    expect(runGate(notFound, "earlier").publish, "tag on an earlier commit, no Release").toBe("false");
  });

  it("stops at a tag whose Release is published", () => {
    expect(runGate(draft("false")).publish, "tag, published Release").toBe("false");
  });

  it("fails on a gh error that is not 'release not found'", () => {
    const result = runGate('echo "HTTP 502" >&2; exit 1');
    expect(result.status, "gate exit status").not.toBe(0);
    expect(result.stderr, "gate stderr").toContain("HTTP 502");
  });
});

it("does not tag or create a Release in a cancelled run", () => {
  const condition = String(job("tag-release").if ?? "");
  expect(condition, "tag-release if").not.toMatch(/\balways\(\)/);
  expect(condition, "tag-release if").toMatch(/!cancelled\(\)/);
  // A desktop leg's timeout-minutes expiry reads `cancelled` in needs; testing it would let a hung leg prevent the tag.
  expect(condition, "tag-release if").not.toMatch(/needs\.desktop\.result/);
});

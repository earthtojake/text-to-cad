import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { appVersion, releaseVersion } from "../../../scripts/app-version.mjs";

const scripts = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "scripts");
const temps: string[] = [];
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

describe("the release version", () => {
  it("is the checkout's VERSION", () => {
    expect(releaseVersion()).toBe(appVersion());
    expect(appVersion()).not.toBe("0.0.0");
  });

  it("refuses the 0.0.0 stand-in a missing VERSION file answers, so packaging cannot ship it", () => {
    expect(() => releaseVersion("0.0.0")).toThrow(/no release version/);
    expect(releaseVersion("1.2.3")).toBe("1.2.3");
  });

  it("stops `package.mjs` before it prepares anything when the checkout has no VERSION", () => {
    // A checkout without VERSION: <repo>/apps/desktop/scripts, and no <repo>/VERSION.
    const repo = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "text-to-cad-package-")));
    temps.push(repo);
    const appRoot = path.join(repo, "apps", "desktop");
    fs.mkdirSync(path.join(appRoot, "scripts"), { recursive: true });
    for (const file of ["package.mjs", "app-version.mjs", "bundle-runtime.mjs", "node-bin.mjs", "python-build.json"]) {
      fs.copyFileSync(path.join(scripts, file), path.join(appRoot, "scripts", file));
    }

    const run = spawnSync(process.execPath, [path.join(appRoot, "scripts", "package.mjs"), "--linux", "--x64"], {
      encoding: "utf8",
      env: { ...process.env, CSC_LINK: "" },
    });

    expect(run.stderr).toContain("no release version");
    expect(run.status).toBe(2);
    expect(run.stdout).not.toContain("packaging text-to-cad 0.0.0");
    // Nothing was created for a build that is not going to happen.
    expect(fs.existsSync(path.join(appRoot, "resources"))).toBe(false);
  });
});

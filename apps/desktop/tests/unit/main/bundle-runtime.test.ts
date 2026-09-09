import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { PYTHON_BUILD, TARGETS, bundledRuntime, hostTarget, pythonBuildUrl, runtimeLayout } from "../../../scripts/bundle-runtime.mjs";
import { bundledPaths, runtimeTarget } from "@main/cad/runtime";

/**
 * The bundler's pin and layout, checked against the resolver's: the script
 * writes what `src/main/cad/runtime.ts` reads, and the two are in different
 * languages with no shared module, so this is where they are held together.
 */
const temps: string[] = [];
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

describe("the pinned interpreter", () => {
  it("names one asset per packaged target, with a hash and pip platform tags for each", () => {
    expect(TARGETS).toEqual(["mac-arm64", "mac-x64", "win-x64", "linux-x64"]);
    for (const target of TARGETS) {
      const asset = PYTHON_BUILD.targets[target];
      expect(asset.file).toContain(`cpython-${PYTHON_BUILD.version}+${PYTHON_BUILD.release}-`);
      expect(asset.file).toMatch(/-install_only\.tar\.gz$/);
      expect(asset.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(asset.pip.platforms.length).toBeGreaterThan(0);
      expect(pythonBuildUrl(target)).toBe(
        `https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD.release}/${asset.file}`,
      );
    }
    // pip matches a manylinux_X_Y tag exactly, so Linux has to list every tag the closure carries.
    expect(PYTHON_BUILD.targets["linux-x64"].pip.platforms).toContain("manylinux2014_x86_64");
    expect(PYTHON_BUILD.targets["linux-x64"].pip.platforms).toContain("manylinux_2_31_x86_64");
  });

  it("names this machine the way electron-builder does", () => {
    expect(hostTarget("darwin", "arm64")).toBe("mac-arm64");
    expect(hostTarget("darwin", "x64")).toBe("mac-x64");
    expect(hostTarget("win32", "x64")).toBe("win-x64");
    expect(hostTarget("linux", "x64")).toBe("linux-x64");
    expect(hostTarget("linux", "arm64")).toBeNull();
    for (const target of TARGETS) {
      const [os, arch] = target.split("-") as [string, string];
      const platform = os === "mac" ? "darwin" : os === "win" ? "win32" : "linux";
      expect(runtimeTarget(platform, arch)).toBe(target);
    }
  });
});

describe("the layout", () => {
  it("lays the interpreter and the marker out where the resolver looks", () => {
    for (const target of TARGETS) {
      const [os, arch] = target.split("-") as [string, string];
      const platform = os === "mac" ? "darwin" : os === "win" ? "win32" : "linux";
      const written = runtimeLayout(path.join("/R", "runtime", target), target);
      const read = bundledPaths("/R", platform, arch);
      expect(written.python).toBe(read.python);
      expect(written.marker).toBe(read.marker);
      expect(written.sitePackages.startsWith(written.pythonDir)).toBe(true);
    }
    expect(runtimeLayout("/R/runtime/win-x64", "win-x64").sitePackages).toBe(path.join("/R/runtime/win-x64", "python", "Lib", "site-packages"));
    expect(runtimeLayout("/R/runtime/mac-arm64", "mac-arm64", "3.13.15").sitePackages).toBe(
      path.join("/R/runtime/mac-arm64", "python", "lib", "python3.13", "site-packages"),
    );
  });

  it("counts a bundle complete only with the marker for this version and target", () => {
    const out = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-bundle-"));
    temps.push(out);
    const layout = runtimeLayout(path.join(out, "mac-arm64"), "mac-arm64");
    expect(bundledRuntime(out, "mac-arm64", "9.9.9")).toBeNull();
    fs.mkdirSync(path.dirname(layout.python), { recursive: true });
    fs.writeFileSync(layout.python, "");
    expect(bundledRuntime(out, "mac-arm64", "9.9.9")).toBeNull();
    fs.writeFileSync(layout.marker, JSON.stringify({ target: "mac-arm64", cadgen: "9.9.8", python: "3.13.15" }));
    expect(bundledRuntime(out, "mac-arm64", "9.9.9")).toBeNull();
    fs.writeFileSync(layout.marker, JSON.stringify({ target: "mac-arm64", cadgen: "9.9.9", python: "3.13.15" }));
    expect(bundledRuntime(out, "mac-arm64", "9.9.9")).toMatchObject({ cadgen: "9.9.9", target: "mac-arm64" });
  });
});

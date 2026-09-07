import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  CadRuntime,
  bundledPaths,
  findCheckout,
  readBundleMarker,
  runtimeLogPath,
  runtimeTarget,
  type ExecResult,
  type RuntimeHost,
} from "@main/cad/runtime";

/**
 * A fake machine: a user-data directory, an optional checkout with a venv,
 * an optional bundled runtime beside the app, and an `exec` that answers the
 * cadgen probe for the interpreters it is told exist.
 */
const temps: string[] = [];
function tempDir(prefix: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  temps.push(dir);
  return dir;
}
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

type Machine = {
  host: RuntimeHost;
  userData: string;
  appRoot: string;
  resources: string;
  execs: Array<{ file: string; args: string[]; env: Record<string, string> }>;
};

function machine(options: {
  checkout?: boolean;
  venv?: boolean;
  /** A complete bundle (marker + interpreter); `"half"` is an interpreter without the marker. */
  bundle?: boolean | "half";
  env?: Record<string, string>;
  override?: string | null;
  cadgenVersions?: Record<string, string | { version: string; viewer: boolean }>;
  platform?: NodeJS.Platform;
  arch?: string;
}): Machine {
  const root = tempDir("hardcore-runtime-");
  const userData = path.join(root, "userData");
  const resources = path.join(root, "resources");
  fs.mkdirSync(userData, { recursive: true });
  fs.mkdirSync(resources, { recursive: true });
  const platform = options.platform ?? "darwin";
  const arch = options.arch ?? "arm64";
  let appRoot = path.join(root, "elsewhere", "app");
  if (options.checkout) {
    const checkout = path.join(root, "checkout");
    fs.mkdirSync(path.join(checkout, "packages", "cadgen", "src"), { recursive: true });
    fs.writeFileSync(path.join(checkout, "VERSION"), "9.9.9\n");
    fs.writeFileSync(path.join(checkout, "packages", "cadgen", "pyproject.toml"), "[project]\nname='cadgen'\n");
    appRoot = path.join(checkout, "apps", "desktop", "out", "main");
    if (options.venv) {
      fs.mkdirSync(path.join(checkout, ".venv", "bin"), { recursive: true });
      fs.writeFileSync(path.join(checkout, ".venv", "bin", "python"), "#!/bin/sh\n");
    }
  }
  fs.mkdirSync(appRoot, { recursive: true });
  const versions: Record<string, { version: string; viewer: boolean }> = {};
  for (const [file, value] of Object.entries(options.cadgenVersions ?? {})) {
    versions[file] = typeof value === "string" ? { version: value, viewer: true } : value;
  }
  if (options.bundle) {
    const bundled = bundledPaths(resources, platform, arch);
    fs.mkdirSync(path.dirname(bundled.python), { recursive: true });
    fs.writeFileSync(bundled.python, "#!/bin/sh\n");
    if (options.bundle === true) {
      fs.writeFileSync(
        bundled.marker,
        JSON.stringify({ target: runtimeTarget(platform, arch), python: "3.13.15", cadgen: "9.9.9", builtAt: "2026-09-06T00:00:00Z" }),
      );
      versions[bundled.python] = versions[bundled.python] ?? { version: "9.9.9", viewer: true };
    }
  }
  const execs: Machine["execs"] = [];

  const host: RuntimeHost = {
    platform,
    arch,
    userData,
    appVersion: "9.9.9",
    resourcesDir: resources,
    appRoot,
    nodeBinary: "/apps/Hardcore.app/Contents/MacOS/Hardcore",
    env: options.env ?? {},
    overrideSetting: () => options.override ?? null,
    exec: async (file, args, execOptions): Promise<ExecResult> => {
      execs.push({ file, args, env: execOptions.env });
      const answer = versions[file];
      if (!answer) {
        return { stdout: "", stderr: "Traceback (most recent call last):\nModuleNotFoundError: No module named 'cadgen'", code: 1 };
      }
      return { stdout: `${JSON.stringify(answer)}\n`, stderr: "", code: 0 };
    },
  };
  return { host, userData, appRoot, resources, execs };
}

describe("the bundled layout", () => {
  it("names the target the way electron-builder does and the interpreter the way the tarball lays it out", () => {
    expect(runtimeTarget("darwin", "arm64")).toBe("mac-arm64");
    expect(runtimeTarget("darwin", "x64")).toBe("mac-x64");
    expect(runtimeTarget("win32", "x64")).toBe("win-x64");
    expect(runtimeTarget("linux", "x64")).toBe("linux-x64");
    expect(bundledPaths("/R", "darwin", "arm64")).toEqual({
      root: "/R/runtime/mac-arm64",
      python: "/R/runtime/mac-arm64/python/bin/python3",
      marker: "/R/runtime/mac-arm64/runtime.json",
    });
    expect(bundledPaths("/R", "win32", "x64").python).toBe(path.join("/R/runtime/win-x64", "python", "python.exe"));
  });

  it("reads the bundler's marker and rejects anything else", () => {
    const dir = tempDir("hardcore-marker-");
    const marker = path.join(dir, "runtime.json");
    fs.writeFileSync(marker, JSON.stringify({ target: "mac-arm64", python: "3.13.15", cadgen: "9.9.9" }));
    expect(readBundleMarker(marker)).toEqual({ target: "mac-arm64", python: "3.13.15", cadgen: "9.9.9" });
    fs.writeFileSync(marker, "{not json");
    expect(readBundleMarker(marker)).toBeNull();
    fs.writeFileSync(marker, JSON.stringify({ cadgen: 1 }));
    expect(readBundleMarker(marker)).toBeNull();
    expect(readBundleMarker(path.join(dir, "missing.json"))).toBeNull();
  });
});

describe("findCheckout", () => {
  it("finds the repository root above the app by VERSION and cadgen's pyproject", () => {
    const m = machine({ checkout: true });
    expect(findCheckout(m.appRoot)).toBe(path.resolve(m.appRoot, "..", "..", "..", ".."));
  });

  it("answers null outside a checkout", () => {
    const m = machine({});
    expect(findCheckout(m.appRoot)).toBeNull();
  });
});

describe("resolution order", () => {
  it("prefers CAD_DESKTOP_PYTHON over everything, and reports it as an override", () => {
    const m = machine({ checkout: true, venv: true, bundle: true, env: { CAD_DESKTOP_PYTHON: "/opt/py/bin/python" }, override: "/setting/python" });
    expect(new CadRuntime(m.host).resolve()).toMatchObject({ python: "/opt/py/bin/python", source: "override" });
  });

  it("then the settings override", () => {
    const m = machine({ checkout: true, venv: true, bundle: true, override: "/setting/python" });
    expect(new CadRuntime(m.host).resolve()).toMatchObject({ python: "/setting/python", source: "override" });
  });

  it("then the bundled runtime beside the app, even inside a checkout with a venv", () => {
    const m = machine({ checkout: true, venv: true, bundle: true });
    const resolved = new CadRuntime(m.host).resolve();
    expect(resolved).toMatchObject({ python: bundledPaths(m.resources, "darwin", "arm64").python, source: "bundled" });
    // The checkout's cadgen source still wins over the bundle's installed copy.
    expect(resolved?.env.PYTHONPATH).toMatch(/packages\/cadgen\/src$/);
  });

  it("does not count an interpreter without the bundler's marker as a runtime", () => {
    const m = machine({ bundle: "half" });
    expect(new CadRuntime(m.host).resolve()).toBeNull();
  });

  it("then a checkout's .venv, with PYTHONPATH pointing at the checkout's cadgen", () => {
    const m = machine({ checkout: true, venv: true });
    const resolved = new CadRuntime(m.host).resolve();
    expect(resolved?.source).toBe("checkout");
    expect(resolved?.python).toMatch(/\.venv\/bin\/python$/);
    expect(resolved?.env.PYTHONPATH).toMatch(/packages\/cadgen\/src$/);
  });

  it("sets PYTHONPATH for an override too, when running from a checkout", () => {
    const m = machine({ checkout: true, override: "/setting/python" });
    expect(new CadRuntime(m.host).resolve()?.env.PYTHONPATH).toMatch(/packages\/cadgen\/src$/);
  });

  it("finds nothing outside a checkout without a bundle", () => {
    const m = machine({});
    expect(new CadRuntime(m.host).resolve()).toBeNull();
  });

  it("looks for python.exe under python/ on Windows", () => {
    const m = machine({ bundle: true, platform: "win32", arch: "x64" });
    expect(new CadRuntime(m.host).resolve()).toMatchObject({
      python: bundledPaths(m.resources, "win32", "x64").python,
      source: "bundled",
    });
  });
});

describe("the process environment", () => {
  it("gives every cadgen process the app's own Node, unbuffered output, and the resolution's PYTHONPATH", () => {
    const m = machine({ checkout: true, venv: true, env: { HOME: "/home/x", PATH: "/usr/bin" } });
    const runtime = new CadRuntime(m.host);
    const env = runtime.processEnv(runtime.resolve()!);
    expect(env).toMatchObject({
      HOME: "/home/x",
      PATH: "/usr/bin",
      PYTHONUNBUFFERED: "1",
      CADGEN_NODE: "/apps/Hardcore.app/Contents/MacOS/Hardcore",
      ELECTRON_RUN_AS_NODE: "1",
    });
    expect(env.PYTHONPATH).toMatch(/packages\/cadgen\/src$/);
  });

  it("leaves a CADGEN_NODE the person set alone", () => {
    const m = machine({ checkout: true, venv: true, env: { CADGEN_NODE: "/opt/node/bin/node" } });
    const runtime = new CadRuntime(m.host);
    const env = runtime.processEnv(runtime.resolve()!);
    expect(env.CADGEN_NODE).toBe("/opt/node/bin/node");
    expect(env.ELECTRON_RUN_AS_NODE).toBeUndefined();
  });

  it("closes the bundled interpreter to the shell's Python variables and never writes bytecode into the bundle", () => {
    const m = machine({
      bundle: true,
      env: { PYTHONPATH: "/somebody/elses/site-packages", PYTHONHOME: "/usr", PYTHONSTARTUP: "/x/rc.py", HOME: "/home/x" },
    });
    const runtime = new CadRuntime(m.host);
    const env = runtime.processEnv(runtime.resolve()!);
    expect(env.PYTHONPATH).toBeUndefined();
    expect(env.PYTHONHOME).toBeUndefined();
    expect(env.PYTHONSTARTUP).toBeUndefined();
    expect(env).toMatchObject({ HOME: "/home/x", PYTHONNOUSERSITE: "1", PYTHONDONTWRITEBYTECODE: "1" });
  });

  it("keeps the shell's PYTHONPATH for a checkout venv, behind the checkout's own source", () => {
    const m = machine({ checkout: true, venv: true, env: { PYTHONPATH: "/extra" } });
    const runtime = new CadRuntime(m.host);
    expect(runtime.processEnv(runtime.resolve()!).PYTHONPATH).toMatch(/packages\/cadgen\/src:\/extra$/);
  });
});

describe("status", () => {
  it("is missing, and says where it looked, with nothing resolved", async () => {
    const m = machine({});
    const status = await new CadRuntime(m.host).status();
    expect(status).toMatchObject({ state: "missing", python: null, source: null, cadgenVersion: null });
    expect(status.message).toContain(bundledPaths(m.resources, "darwin", "arm64").root);
    expect(status.message).toContain("not running from a checkout");
  });

  it("is ready with the bundle's version and viewer flag, probed once", async () => {
    const m = machine({ bundle: true });
    const runtime = new CadRuntime(m.host);
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    expect(await runtime.status()).toMatchObject({
      state: "ready",
      python,
      source: "bundled",
      cadgenVersion: "9.9.9",
      viewerBuilt: true,
      log: null,
    });
    await runtime.status();
    expect(m.execs.filter((exec) => exec.file === python)).toHaveLength(1);
    // The probe ran the interpreter closed to the shell and told it not to write pycs.
    expect(m.execs[0]?.env).toMatchObject({ PYTHONNOUSERSITE: "1", PYTHONDONTWRITEBYTECODE: "1" });
  });

  it("reports a cadgen whose viewer does not import as not viewer-built", async () => {
    const m = machine({ bundle: true });
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    (m.host as { exec: RuntimeHost["exec"] }).exec = async () => ({
      stdout: `${JSON.stringify({ version: "9.9.9", viewer: false })}\n`,
      stderr: "",
      code: 0,
    });
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("ready");
    expect(status.python).toBe(python);
    expect(status.viewerBuilt).toBe(false);
  });

  it("is an error, with the interpreter's words and the log, when cadgen does not import", async () => {
    const m = machine({ override: "/setting/python" });
    fs.writeFileSync(path.join(m.userData, "python"), "");
    (m.host as { overrideSetting: () => string | null }).overrideSetting = () => path.join(m.userData, "python");
    const runtime = new CadRuntime(m.host);
    const status = await runtime.status();
    expect(status.state).toBe("error");
    expect(status.source).toBe("override");
    expect(status.message).toContain("The override interpreter");
    expect(status.message).toContain("No module named 'cadgen'");
    // The failure was written to the runtime log, which the status points at.
    const log = runtimeLogPath(m.userData);
    expect(status.log).toBe(log);
    expect(fs.readFileSync(log, "utf8")).toContain("No module named 'cadgen'");
  });

  it("is an error naming a missing override path", async () => {
    const m = machine({ override: "/nowhere/python" });
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.message).toContain("/nowhere/python");
  });

  it("does not remember a failed probe, and repair probes again", async () => {
    const m = machine({ bundle: true });
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    // First the bundle answers with an error; then it is fixed.
    let broken = true;
    const exec = m.host.exec;
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args, options) =>
      broken ? { stdout: "", stderr: "ImportError: dlopen failed", code: 1 } : exec(file, args, options);
    const runtime = new CadRuntime(m.host);
    expect((await runtime.status()).state).toBe("error");
    broken = false;
    expect((await runtime.repair()).state).toBe("ready");
    expect((await runtime.ready())?.python).toBe(python);
  });

  it("ready() answers the interpreter only when it probes", async () => {
    const good = machine({ bundle: true });
    expect((await new CadRuntime(good.host).ready())?.source).toBe("bundled");
    const bad = machine({ override: "/nowhere/python" });
    expect(await new CadRuntime(bad.host).ready()).toBeNull();
    const none = machine({});
    expect(await new CadRuntime(none.host).ready()).toBeNull();
  });
});

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterAll, afterEach, describe, expect, it } from "vitest";

import {
  CadRuntime,
  execCommand,
  bundledPaths,
  findCheckout,
  readBundleMarker,
  runtimeBinDir,
  runtimeLogPath,
  runtimeTarget,
  type ExecResult,
  type RuntimeHost,
} from "@main/cad/runtime";

// Writable first, so a read-only file (a fake interpreter, a marker) cannot stop the removal.
import { removeTree } from "./temp-dirs";

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

/**
 * Every runtime-log write a test started. The runtime logs without awaiting
 * (`void this.log(...)`), and `log` creates `userData/` again, so removing
 * the directories before those writes land leaves `text-to-cad-runtime-*`
 * behind in the temp directory. Cleanup waits for them first.
 */
const logWrites: Promise<void>[] = [];
const log = CadRuntime.prototype.log;
CadRuntime.prototype.log = function (this: CadRuntime, line: string) {
  const write = log.call(this, line);
  logWrites.push(write);
  return write;
};

async function cleanUp(): Promise<void> {
  // A write can start another (a probe's handler); drain until none is left.
  while (logWrites.length > 0) {
    await Promise.allSettled(logWrites.splice(0));
  }
  for (const dir of temps.splice(0)) {
    removeTree(dir);
  }
}
afterEach(cleanUp);
afterAll(async () => {
  await cleanUp();
  CadRuntime.prototype.log = log;
});

type Machine = {
  host: RuntimeHost;
  userData: string;
  appRoot: string;
  resources: string;
  execs: Array<{ file: string; args: string[]; env: Record<string, string> }>;
};

/** What `python -m cadgen.cli doctor --json` prints for an install. */
function doctorReport(answer: { version: string; viewer: boolean }, kernel: { ok: boolean; state: string; error: string | null } = { ok: true, state: "ok", error: null }) {
  return {
    version: answer.version,
    python: "3.13.15",
    install: "/site/cadgen",
    viewer: { ok: answer.viewer, error: answer.viewer ? null : "ImportError: no viewer" },
    kernel: { ...kernel, path: kernel.state === "ok" || kernel.state === "unsupported" ? "/site/OCP/__init__.py" : null },
    pin: { state: "none", file: null, pinned: null },
  };
}

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
  const root = tempDir("text-to-cad-runtime-");
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
    nodeBinary: "/apps/text-to-cad.app/Contents/MacOS/text-to-cad",
    packaged: false,
    env: options.env ?? {},
    overrideSetting: () => options.override ?? null,
    exec: async (file, args, execOptions): Promise<ExecResult> => {
      execs.push({ file, args, env: execOptions.env });
      const answer = versions[file];
      if (!answer) {
        return { stdout: "", stderr: "Traceback (most recent call last):\nModuleNotFoundError: No module named 'cadgen'", code: 1 };
      }
      return { stdout: `${JSON.stringify(doctorReport(answer))}\n`, stderr: "", code: 0 };
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
    const dir = tempDir("text-to-cad-marker-");
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

describe("what a session's PATH gets", () => {
  it("names the directory an interpreter's console scripts live in, per platform", () => {
    expect(runtimeBinDir("/R/runtime/mac-arm64/python/bin/python3", "darwin")).toBe("/R/runtime/mac-arm64/python/bin");
    expect(runtimeBinDir("/proj/.venv/bin/python", "linux")).toBe("/proj/.venv/bin");
    // Windows: pip writes them to Scripts/ beside the interpreter…
    expect(runtimeBinDir("R:\\runtime\\win-x64\\python\\python.exe", "win32")).toBe(
      path.win32.join("R:\\runtime\\win-x64\\python", "Scripts"),
    );
    // …except in a venv, where the interpreter is already in Scripts/.
    expect(runtimeBinDir("R:\\proj\\.venv\\Scripts\\python.exe", "win32")).toBe("R:\\proj\\.venv\\Scripts");
  });

  it("is the checkout venv's bin when pip put a cadgen there", () => {
    const fake = machine({ checkout: true, venv: true });
    const venvBin = path.join(findCheckout(fake.appRoot)!, ".venv", "bin");
    fs.writeFileSync(path.join(venvBin, "cadgen"), "#!/bin/sh\n");
    expect(new CadRuntime(fake.host).sessionPath()).toEqual([venvBin]);
  });

  /**
   * The bundled runtime is a `pip install --target`, and the bundler prunes
   * the console scripts pip wrote there — so `cadgen` has to be written for
   * it, or a packaged app's session would have `python` and no `cadgen`. The
   * bundle's own bin is NOT on the PATH: only launchers for `cadgen`,
   * `python3` and `python`, so nothing else in the signed bundle (pip, idle,
   * python3-config) is what an agent's `pip` or `python3-config` means.
   */
  it("is only the app's launchers for cadgen, python3 and python with the bundled runtime", () => {
    const fake = machine({ bundle: true });
    const runtime = new CadRuntime(fake.host);
    const bundled = bundledPaths(fake.resources, "darwin", "arm64");

    const dirs = runtime.sessionPath();

    const bin = path.join(fake.userData, "bin");
    expect(dirs).toEqual([bin]);
    const launcher = path.join(bin, "cadgen");
    expect(fs.readFileSync(launcher, "utf8")).toBe(`#!/bin/sh\nexec "${bundled.python}" -m cadgen.cli "$@"\n`);
    expect(fs.statSync(launcher).mode & 0o111).toBeTruthy();
    for (const name of ["python3", "python"]) {
      const shim = path.join(bin, name);
      expect(fs.readFileSync(shim, "utf8")).toBe(`#!/bin/sh\nexec "${bundled.python}" "$@"\n`);
      expect(fs.statSync(shim).mode & 0o111).toBeTruthy();
    }
    expect(fs.readdirSync(bin).sort()).toEqual(["cadgen", "python", "python3"]);

    // Asked again with nothing changed: the same answer, the same file.
    const before = fs.statSync(launcher).mtimeMs;
    expect(runtime.sessionPath()).toEqual(dirs);
    expect(fs.statSync(launcher).mtimeMs).toBe(before);
  });

  it("writes .cmd launchers on Windows", () => {
    const fake = machine({ bundle: true, platform: "win32", arch: "x64" });
    const dirs = new CadRuntime(fake.host).sessionPath();
    const bin = path.join(fake.userData, "bin");
    expect(dirs).toEqual([bin]);
    expect(fs.readFileSync(path.join(bin, "cadgen.cmd"), "utf8")).toContain("-m cadgen.cli %*");
    expect(fs.readFileSync(path.join(bin, "python.cmd"), "utf8")).toMatch(/python\.exe" %\*\r\n$/);
    expect(fs.existsSync(path.join(bin, "python3.cmd"))).toBe(true);
  });

  it("keeps an override interpreter's own bin after the cadgen launcher", () => {
    const fake = machine({ bundle: true, env: {} });
    // The bundled runtime first, so its python shims exist…
    new CadRuntime(fake.host).sessionPath();
    expect(fs.existsSync(path.join(fake.userData, "bin", "python3"))).toBe(true);
    // …and then an override, whose own python must not be shadowed by them.
    fake.host.env.CAD_DESKTOP_PYTHON = "/opt/py/bin/python3";
    expect(new CadRuntime(fake.host).sessionPath()).toEqual([path.join(fake.userData, "bin"), "/opt/py/bin"]);
    expect(fs.existsSync(path.join(fake.userData, "bin", "python3"))).toBe(false);
    expect(fs.existsSync(path.join(fake.userData, "bin", "python"))).toBe(false);
  });

  it("is empty when there is no runtime at all", () => {
    expect(new CadRuntime(machine({}).host).sessionPath()).toEqual([]);
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
      CADGEN_NODE: "/apps/text-to-cad.app/Contents/MacOS/text-to-cad",
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

  it("tells an installed copy to reinstall, without naming a build script; a checkout keeps the pointer", async () => {
    const m = machine({});
    (m.host as { packaged: boolean }).packaged = true;
    const packaged = (await new CadRuntime(m.host).status()).message;
    expect(packaged).toContain("Reinstall");
    expect(packaged).not.toContain("scripts/");
    m.host.packaged = false;
    expect((await new CadRuntime(m.host).status()).message).toContain("scripts/bundle-runtime.mjs");
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
      stdout: `${JSON.stringify(doctorReport({ version: "9.9.9", viewer: false }))}\n`,
      stderr: "",
      code: 0,
    });
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("ready");
    expect(status.python).toBe(python);
    expect(status.viewerBuilt).toBe(false);
  });

  it("cuts the runtime log back in place once it passes its cap, keeping the newest lines", async () => {
    const m = machine({});
    const log = runtimeLogPath(m.userData);
    const line = `${"x".repeat(1023)}\n`;
    fs.writeFileSync(log, line.repeat(4 * 1024 + 8));
    const before = fs.statSync(log).ino;
    const runtime = new CadRuntime(m.host);
    await runtime.log("newest line");
    expect(fs.statSync(log).size).toBeLessThanOrEqual(4 * 1024 * 1024);
    expect(fs.statSync(log).size).toBeLessThanOrEqual(1024 * 1024 + 128);
    // The same file, so the daemon's append fd is still on it.
    expect(fs.statSync(log).ino).toBe(before);
    const text = fs.readFileSync(log, "utf8");
    expect(text.endsWith("newest line\n")).toBe(true);
    expect(text.startsWith("x")).toBe(true);
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

  it.skipIf(process.platform === "win32")(
    "is ready with a kernel warning, in cadgen's words, when cadgen's kernel check refuses the OCP it found",
    async () => {
      // A real interpreter process: cadgen and its viewer import, but
      // `cadgen doctor --json` says its kernel check refuses the OCP it found
      // (one from another distribution). The viewer never imports the kernel,
      // so the runtime is ready — and says, rather than hides, that a STEP
      // build may fail. Asked only whether cadgen imports, it said plain Ready.
      const kernelError =
        "ValueError: op memo requires the cadquery-ocp-novtk distribution for persistent reuse " +
        "(PackageNotFoundError: No package metadata was found for cadquery-ocp-novtk)";
      const python = path.join(tempDir("text-to-cad-fake-python-"), "python");
      fs.writeFileSync(
        python,
        [
          "#!/bin/sh",
          'if [ "$3" = doctor ] && [ "$CADGEN_DOCTOR_KERNEL_TIMEOUT" = 90 ]; then',
          `  echo '${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }, { ok: false, state: "unsupported", error: kernelError }))}'`,
          "  exit 0",
          "fi",
          "echo 'unexpected probe' >&2",
          "exit 1",
          "",
        ].join("\n"),
        { mode: 0o755 },
      );
      const m = machine({ env: { CAD_DESKTOP_PYTHON: python } });
      (m.host as { exec: RuntimeHost["exec"] }).exec = (file, args, options) => execCommand(file, args, options);
      const runtime = new CadRuntime(m.host);
      const status = await runtime.status();
      expect(status).toMatchObject({
        state: "ready",
        source: "override",
        cadgenVersion: "9.9.9",
        kernel: { state: "unsupported", message: kernelError },
      });
      expect(status.log).toBe(runtimeLogPath(m.userData));
      expect(fs.readFileSync(runtimeLogPath(m.userData), "utf8")).toContain("CAD kernel unsupported");
      // GLB, STL and DXF still open: the viewer is started on it.
      expect((await runtime.ready())?.python).toBe(python);
    },
  );

  it("is an error when the CAD kernel fails to load, because every build would", async () => {
    const m = machine({ bundle: true });
    const refused = "ImportError: DLL load failed while importing OCP: Access is denied.";
    (m.host as { exec: RuntimeHost["exec"] }).exec = async () => ({
      stdout: `${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }, { ok: false, state: "failed", error: refused }))}\n`,
      stderr: "",
      code: 4,
    });
    const runtime = new CadRuntime(m.host);
    const status = await runtime.status();
    expect(status.state).toBe("error");
    expect(status.message).toContain("its CAD kernel fails to load");
    expect(status.message).toContain(refused);
    expect(status.kernel).toBeUndefined();
    expect(await runtime.ready()).toBeNull();
  });

  it("gives the doctor its own deadline, a shorter one for its kernel child, and its own process group", async () => {
    const m = machine({ bundle: true });
    const seen: Parameters<RuntimeHost["exec"]>[2][] = [];
    const exec = m.host.exec;
    (m.host as { exec: RuntimeHost["exec"] }).exec = (file, args, options) => {
      seen.push(options);
      return exec(file, args, options);
    };
    await new CadRuntime(m.host).status();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ timeoutMs: 120_000, processGroup: true });
    expect(Number(seen[0]?.env.CADGEN_DOCTOR_KERNEL_TIMEOUT) * 1000).toBeLessThan(120_000);
  });

  it("says a doctor that timed out did not answer, and does not ask again the slow way", async () => {
    const m = machine({ bundle: true });
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      return { stdout: "", stderr: "", code: null, timedOut: true };
    };
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.message).toContain("cadgen doctor did not answer within 120 s");
    expect(status.message).not.toContain("exited null");
    expect(m.execs).toHaveLength(1);
  });

  it.each([
    ["a doctor without --json", "usage: cadgen doctor [-h] [requirements]\ncadgen doctor: error: unrecognized arguments: --json", 2],
    ["a cadgen with no cadgen.cli entry", "/python: No module named cadgen.cli.__main__; 'cadgen.cli' is a package and cannot be directly executed", 1],
    ["a cadgen with no cadgen.cli package", "/python: Error while finding module specification for 'cadgen.cli' (ModuleNotFoundError: No module named 'cadgen.cli')", 1],
  ])("asks %s the old way, kernel imported by name", async (_name, stderr, code) => {
    const m = machine({ bundle: true });
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    let ocp: "missing" | "refused" | "ok" = "missing";
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      if (args.includes("--json")) {
        return { stdout: "", stderr, code };
      }
      const kernel = {
        missing: "ModuleNotFoundError: No module named 'OCP'",
        refused: "ImportError: dlopen(OCP.so): Symbol not found",
        ok: null,
      }[ocp];
      return { stdout: `${JSON.stringify({ version: "0.4.0", viewer: true, kernel })}\n`, stderr: "", code: 0 };
    };
    const runtime = new CadRuntime(m.host);
    expect(await runtime.status()).toMatchObject({
      state: "ready",
      cadgenVersion: "0.4.0",
      kernel: { state: "missing", message: "ModuleNotFoundError: No module named 'OCP'" },
    });
    expect(m.execs.map((exec) => exec.args[0])).toEqual(["-m", "-c"]);
    ocp = "refused";
    expect((await runtime.repair()).state).toBe("error");
    ocp = "ok";
    const ready = await runtime.repair();
    expect(ready).toMatchObject({ state: "ready", python, cadgenVersion: "0.4.0" });
    expect(ready.kernel).toBeUndefined();
  });

  it("asks a doctor whose report has no kernel the old way too", async () => {
    const m = machine({ bundle: true });
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      return args.includes("--json")
        ? { stdout: `${JSON.stringify({ version: "0.6.0", python: "3.13", install: "/site/cadgen" })}\n`, stderr: "", code: 0 }
        : { stdout: `${JSON.stringify({ version: "0.6.0", viewer: true, kernel: null })}\n`, stderr: "", code: 0 };
    };
    expect(await new CadRuntime(m.host).status()).toMatchObject({ state: "ready", cadgenVersion: "0.6.0" });
    expect(m.execs.map((exec) => exec.args[0])).toEqual(["-m", "-c"]);
  });

  it.each([
    ["crashed", { stdout: "", stderr: "Traceback (most recent call last):\nImportError: cannot import name 'kernel_status' from 'cadgen.cli.doctor'", code: 1 }, "cannot import name 'kernel_status'"],
    ["was killed by a signal", { stdout: "", stderr: "", code: null }, "python was killed"],
  ])("does not mask a doctor that %s with the old way: that is the failure, in its words, logged first", async (_name, answer, words) => {
    const m = machine({ bundle: true });
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      return args.includes("--json")
        ? answer
        : { stdout: `${JSON.stringify({ version: "9.9.9", viewer: true, kernel: null })}\n`, stderr: "", code: 0 };
    };
    const runtime = new CadRuntime(m.host);
    const status = await runtime.status();
    expect(status.state).toBe("error");
    expect(status.message).toContain(words);
    expect(m.execs).toHaveLength(1);
    const log = fs.readFileSync(runtimeLogPath(m.userData), "utf8").split("\n").find((line) => line.includes("gave no report"));
    expect(log).toContain(words);
    expect(await runtime.ready()).toBeNull();
  });

  it("is ready with a timeout warning when the kernel check did not finish, not remembered, and the daemon still warms", async () => {
    const m = machine({ bundle: true });
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    let slow = true;
    const words = "timed out after 90 s";
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      const kernel = slow ? { ok: false, state: "timeout", error: words } : { ok: true, state: "ok", error: null };
      return { stdout: `${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }, kernel))}\n`, stderr: "", code: slow ? 4 : 0 };
    };
    const runtime = new CadRuntime(m.host);
    expect(await runtime.status()).toMatchObject({ state: "ready", kernel: { state: "timeout", message: words } });
    // Not a verdict on the kernel: the viewer starts, and so may the daemon.
    expect((await runtime.ready())?.python).toBe(python);
    expect((await runtime.daemonReady())?.python).toBe(python);
    // Not cached either: every one of those asked again.
    expect(m.execs).toHaveLength(3);
    slow = false;
    const next = await runtime.status();
    expect(next.state).toBe("ready");
    expect(next.kernel).toBeUndefined();
    await runtime.status();
    expect(m.execs).toHaveLength(4);
  });

  it("does not let a stale probe's late failure evict the newer probe an invalidate() started", async () => {
    const m = machine({ bundle: true });
    const answers: Array<(result: ExecResult) => void> = [];
    (m.host as { exec: RuntimeHost["exec"] }).exec = (file, args) => {
      m.execs.push({ file, args, env: {} });
      return new Promise((resolve) => answers.push(resolve));
    };
    const runtime = new CadRuntime(m.host);
    const stale = runtime.status();
    await Promise.resolve();
    runtime.invalidate();
    const fresh = runtime.status();
    await Promise.resolve();
    expect(answers).toHaveLength(2);
    answers[1]!({ stdout: `${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }))}\n`, stderr: "", code: 0 });
    expect((await fresh).state).toBe("ready");
    answers[0]!({ stdout: "", stderr: "Traceback (most recent call last):\nRuntimeError: stale", code: 1 });
    expect((await stale).state).toBe("error");
    // The newer answer is still the remembered one.
    expect((await runtime.status()).state).toBe("ready");
    expect(m.execs).toHaveLength(2);
  });

  it("reads the report even when something prints after it", async () => {
    const m = machine({ bundle: true });
    (m.host as { exec: RuntimeHost["exec"] }).exec = async () => ({
      stdout: `sitecustomize: hello\n${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }))}\n{"atexit": true}\nbye from atexit\n`,
      stderr: "",
      code: 0,
    });
    expect(await new CadRuntime(m.host).status()).toMatchObject({ state: "ready", cadgenVersion: "9.9.9" });
  });

  it("says plainly that cadgen is not installed, rather than calling it an older cadgen", async () => {
    const m = machine({ bundle: true });
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      return { stdout: "", stderr: `${python}: Error while finding module specification for 'cadgen.cli' (ModuleNotFoundError: No module named 'cadgen')`, code: 1 };
    };
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.message).toContain(`cadgen is not installed in ${python}`);
    expect(status.message).not.toContain("Error while finding module specification");
    expect(m.execs).toHaveLength(1);
  });

  it("answers a changed override with the new interpreter's own probe, not the old one's kernel note", async () => {
    const m = machine({});
    const dir = tempDir("text-to-cad-overrides-");
    const [oldPython, newPython] = [path.join(dir, "old"), path.join(dir, "new")];
    fs.writeFileSync(oldPython, "");
    fs.writeFileSync(newPython, "");
    let override = oldPython;
    (m.host as { overrideSetting: () => string | null }).overrideSetting = () => override;
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      const kernel = file === oldPython ? { ok: false, state: "missing", error: "ModuleNotFoundError: No module named 'OCP'" } : undefined;
      return { stdout: `${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }, kernel))}\n`, stderr: "", code: 0 };
    };
    const runtime = new CadRuntime(m.host);
    expect((await runtime.status()).kernel?.state).toBe("missing");
    override = newPython;
    const fresh = await runtime.repair();
    expect(fresh).toMatchObject({ state: "ready", python: newPython });
    expect(fresh.kernel).toBeUndefined();
    expect(m.execs.map((exec) => exec.file)).toEqual([oldPython, newPython]);
  });

  it("does not warm the build daemon on a runtime with a kernel warning, and says so once", async () => {
    const m = machine({ bundle: true });
    const python = bundledPaths(m.resources, "darwin", "arm64").python;
    let kernel: { ok: boolean; state: string; error: string | null } = { ok: false, state: "missing", error: "ModuleNotFoundError: No module named 'OCP'" };
    (m.host as { exec: RuntimeHost["exec"] }).exec = async () => ({
      stdout: `${JSON.stringify(doctorReport({ version: "9.9.9", viewer: true }, kernel))}\n`,
      stderr: "",
      code: 0,
    });
    const runtime = new CadRuntime(m.host);
    expect(await runtime.daemonReady()).toBeNull();
    expect(await runtime.daemonReady()).toBeNull();
    // The viewer is still warmed on it.
    expect((await runtime.ready())?.python).toBe(python);
    await runtime.log("flush");
    const skipped = fs.readFileSync(runtimeLogPath(m.userData), "utf8").split("\n").filter((line) => line.includes("[daemon] not warmed"));
    expect(skipped).toHaveLength(1);
    expect(skipped[0]).toContain("CAD kernel missing");
    kernel = { ok: true, state: "ok", error: null };
    await runtime.repair();
    expect((await runtime.daemonReady())?.python).toBe(python);
  });

  it("throws only when the old way fails too, in its words", async () => {
    const m = machine({ bundle: true });
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (_file, args) =>
      args.includes("--json")
        ? { stdout: "", stderr: "No module named cadgen.cli.__main__", code: 1 }
        : { stdout: "", stderr: "Traceback (most recent call last):\nModuleNotFoundError: No module named 'cadgen'", code: 1 };
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.message).toContain("No module named 'cadgen'");
  });

  it("is an error naming a missing override path", async () => {
    const m = machine({ override: "/nowhere/python" });
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.message).toContain("/nowhere/python");
  });

  it("runs a failing doctor once per window; repair() and the window's end ask again", async () => {
    const m = machine({ bundle: true });
    let now = 1_000;
    (m.host as { now?: () => number }).now = () => now;
    (m.host as { exec: RuntimeHost["exec"] }).exec = async (file, args) => {
      m.execs.push({ file, args, env: {} });
      return { stdout: "", stderr: "ImportError: dlopen failed", code: 1 };
    };
    const runtime = new CadRuntime(m.host);
    for (let bind = 0; bind < 5; bind += 1) {
      expect(await runtime.daemonReady()).toBeNull();
      expect(await runtime.ready()).toBeNull();
    }
    expect(m.execs).toHaveLength(1);
    await runtime.repair();
    expect(m.execs).toHaveLength(2);
    await runtime.ready();
    expect(m.execs).toHaveLength(2);
    now += 61_000;
    await runtime.ready();
    expect(m.execs).toHaveLength(3);
  });

  it("does not remember a failed probe past repair, which probes again", async () => {
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

describe("execCommand", () => {
  it.skipIf(process.platform === "win32")(
    "says a timeout is one, and ends the grandchildren of a process-group run with it",
    async () => {
      // The doctor's shape: a leader that starts a child and waits on it. A
      // timeout kills the leader; the group takes the child down with it
      // instead of leaving it orphaned for its own, longer timeout.
      const dir = tempDir("text-to-cad-group-");
      const script = path.join(dir, "leader");
      const pidFile = path.join(dir, "child.pid");
      fs.writeFileSync(script, `#!/bin/sh\nsleep 30 &\necho $! > "${pidFile}"\nwait\n`, { mode: 0o755 });
      const result = await execCommand(script, [], {
        env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
        timeoutMs: 500,
        processGroup: true,
      });
      expect(result.timedOut).toBe(true);
      expect(result.code).toBeNull();
      const child = Number(fs.readFileSync(pidFile, "utf8").trim());
      const alive = () => {
        try {
          process.kill(child, 0);
          return true;
        } catch {
          return false;
        }
      };
      while (alive()) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      expect(alive()).toBe(false);
    },
  );

  it.skipIf(process.platform === "win32")("decodes a UTF-8 character split across two chunks as the character", async () => {
    const script = path.join(tempDir("text-to-cad-utf8-"), "split");
    // "€" is E2 82 AC; its bytes arrive in two writes, a pause apart.
    fs.writeFileSync(script, "#!/bin/sh\nprintf '\\342\\202' >&2\nsleep 0.2\nprintf '\\254 ok\\n' >&2\n", { mode: 0o755 });
    const lines: string[] = [];
    const result = await execCommand(script, [], { env: { PATH: process.env.PATH ?? "/usr/bin:/bin" }, onLine: (line) => lines.push(line) });
    expect(result.stderr).toBe("€ ok\n");
    expect(lines).toEqual(["€ ok"]);
  });
});

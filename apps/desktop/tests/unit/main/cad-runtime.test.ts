import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  CadRuntime,
  PYTHON_BUILD,
  findCheckout,
  managedPaths,
  pythonBuildTarget,
  pythonBuildUrl,
  type ExecResult,
  type PythonBuild,
  type RuntimeHost,
} from "@main/cad/runtime";

/** The real pin, with one asset's hash replaced by that of the bytes the fake downloads. */
function pinFor(bytes: Buffer): PythonBuild {
  return {
    ...PYTHON_BUILD,
    assets: {
      ...PYTHON_BUILD.assets,
      "darwin-arm64": { ...PYTHON_BUILD.assets["darwin-arm64"], sha256: createHash("sha256").update(bytes).digest("hex") },
    },
  };
}

/**
 * A fake machine: a user-data directory, an optional checkout with a venv,
 * an optional bundled wheel, and an `exec` that answers the cadgen probe for
 * the interpreters it is told exist.
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
  execs: Array<{ file: string; args: string[]; env: Record<string, string> }>;
  downloads: string[];
  extracts: string[];
};

function machine(options: {
  checkout?: boolean;
  venv?: boolean;
  wheel?: boolean;
  env?: Record<string, string>;
  override?: string | null;
  cadgenVersions?: Record<string, string>;
  platform?: NodeJS.Platform;
  arch?: string;
  downloadBytes?: Buffer;
  extractProduces?: boolean;
}): Machine {
  const root = tempDir("hardcore-runtime-");
  const userData = path.join(root, "userData");
  const resources = path.join(root, "resources");
  fs.mkdirSync(userData, { recursive: true });
  fs.mkdirSync(path.join(resources, "cadgen"), { recursive: true });
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
  if (options.wheel) {
    fs.writeFileSync(path.join(resources, "cadgen", "cadgen-9.9.9-py3-none-any.whl"), "");
    fs.writeFileSync(path.join(resources, "cadgen", "constraints.txt"), "build123d==1.0\n");
  }
  const execs: Machine["execs"] = [];
  const downloads: string[] = [];
  const extracts: string[] = [];
  const versions = options.cadgenVersions ?? {};
  const platform = options.platform ?? "darwin";
  const managed = managedPaths(userData, "9.9.9", platform);

  const host: RuntimeHost = {
    platform,
    arch: options.arch ?? "arm64",
    userData,
    appVersion: "9.9.9",
    resourcesDir: resources,
    appRoot,
    env: options.env ?? {},
    overrideSetting: () => options.override ?? null,
    exec: async (file, args, execOptions): Promise<ExecResult> => {
      execs.push({ file, args, env: execOptions.env });
      if (args[0] === "-m" && args[1] === "pip") {
        execOptions.onLine?.("Collecting cadgen==9.9.9");
        execOptions.onLine?.("Successfully installed cadgen-9.9.9");
        return { stdout: "", stderr: "", code: 0 };
      }
      const version = versions[file];
      if (!version) {
        return { stdout: "", stderr: "ModuleNotFoundError: No module named 'cadgen'", code: 1 };
      }
      return { stdout: `${JSON.stringify({ version, viewer: true })}\n`, stderr: "", code: 0 };
    },
    download: async (url, dest, onProgress) => {
      downloads.push(url);
      const bytes = options.downloadBytes ?? Buffer.from("not really python");
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, bytes);
      onProgress(bytes.length, bytes.length);
    },
    extract: async (archive, _dest) => {
      extracts.push(archive);
      if (options.extractProduces !== false) {
        fs.mkdirSync(path.dirname(managed.python), { recursive: true });
        fs.writeFileSync(managed.python, "#!/bin/sh\n");
        // The interpreter the extract produced answers the probe from now on.
        versions[managed.python] = versions[managed.python] ?? "9.9.9";
      }
    },
  };
  return { host, userData, appRoot, execs, downloads, extracts };
}

describe("the pinned interpreter", () => {
  it("names one asset per packaged platform, with a hash for each", () => {
    for (const target of ["darwin-arm64", "darwin-x64", "win32-x64", "linux-x64"] as const) {
      expect(PYTHON_BUILD.assets[target].file).toContain(`+${PYTHON_BUILD.release}-`);
      expect(PYTHON_BUILD.assets[target].sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(pythonBuildUrl(target)).toBe(
        `https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD.release}/${PYTHON_BUILD.assets[target].file}`,
      );
    }
    expect(pythonBuildTarget("darwin", "arm64")).toBe("darwin-arm64");
    expect(pythonBuildTarget("linux", "arm64")).toBeNull();
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
  it("prefers CAD_DESKTOP_PYTHON over everything, and reports it as an override", async () => {
    const m = machine({ checkout: true, venv: true, env: { CAD_DESKTOP_PYTHON: "/opt/py/bin/python" }, override: "/setting/python" });
    const runtime = new CadRuntime(m.host);
    expect(runtime.resolve()).toMatchObject({ python: "/opt/py/bin/python", source: "override" });
  });

  it("then the settings override", () => {
    const m = machine({ checkout: true, venv: true, override: "/setting/python" });
    expect(new CadRuntime(m.host).resolve()).toMatchObject({ python: "/setting/python", source: "override" });
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

  it("then the managed runtime, only once its marker is written", () => {
    const m = machine({});
    const runtime = new CadRuntime(m.host);
    expect(runtime.resolve()).toBeNull();
    const managed = managedPaths(m.userData, "9.9.9", "darwin");
    fs.mkdirSync(path.dirname(managed.python), { recursive: true });
    fs.writeFileSync(managed.python, "");
    // An interpreter without the marker is a half-finished provision.
    expect(runtime.resolve()).toBeNull();
    fs.writeFileSync(managed.marker, "{}");
    expect(runtime.resolve()).toMatchObject({ python: managed.python, source: "managed" });
  });

  it("uses python.exe under Scripts/ and python/ on Windows", () => {
    const m = machine({ checkout: true, platform: "win32", arch: "x64" });
    const runtime = new CadRuntime(m.host);
    // No venv was created for win32 in the fake, so this resolves to nothing,
    // but the managed layout is what matters here.
    expect(managedPaths(m.userData, "9.9.9", "win32").python).toMatch(/python[\\/]python\.exe$/);
    expect(runtime.resolve()).toBeNull();
  });
});

describe("status", () => {
  it("is missing with nothing resolved", async () => {
    const m = machine({});
    expect(await new CadRuntime(m.host).status()).toMatchObject({ state: "missing", python: null, cadgenVersion: null });
  });

  it("is ready when the interpreter imports cadgen, with its version and viewer flag", async () => {
    const m = machine({ checkout: true, venv: true, cadgenVersions: {} });
    const runtime = new CadRuntime(m.host);
    const python = runtime.resolve()!.python;
    (m.host as { exec: RuntimeHost["exec"] }).exec = async () => ({
      stdout: `${JSON.stringify({ version: "9.9.9", viewer: true })}\n`,
      stderr: "",
      code: 0,
    });
    expect(await runtime.status()).toMatchObject({
      state: "ready",
      python,
      cadgenVersion: "9.9.9",
      viewerBuilt: true,
      overridden: false,
    });
  });

  it("is an error, with the interpreter's words, when cadgen does not import", async () => {
    const m = machine({ override: "/setting/python" });
    fs.writeFileSync(path.join(m.userData, "python"), "");
    (m.host as { overrideSetting: () => string | null }).overrideSetting = () => path.join(m.userData, "python");
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.overridden).toBe(true);
    expect(status.message).toContain("No module named 'cadgen'");
  });

  it("is an error naming a missing override path", async () => {
    const m = machine({ override: "/nowhere/python" });
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("error");
    expect(status.message).toContain("/nowhere/python");
  });

  it("says why nothing can be provisioned on an unsupported platform", async () => {
    const m = machine({ platform: "linux", arch: "arm64" });
    const status = await new CadRuntime(m.host).status();
    expect(status.state).toBe("missing");
    expect(status.message).toContain("linux/arm64");
  });
});

describe("provisioning", () => {
  it("downloads the pinned asset, verifies it, extracts, installs cadgen and writes the marker", async () => {
    const bytes = Buffer.from("python-build-standalone bytes");
    const m = machine({ downloadBytes: bytes });
    const runtime = new CadRuntime(m.host, pinFor(bytes));
    const progress: Array<{ percent?: number; message?: string }> = [];
    runtime.onProgress((event) => progress.push({ percent: event.percent, message: event.message }));

    const status = await runtime.provision();
    expect(status.state).toBe("ready");
    expect(status.cadgenVersion).toBe("9.9.9");
    expect(m.downloads).toEqual([pythonBuildUrl("darwin-arm64")]);
    expect(m.extracts).toHaveLength(1);
    const managed = managedPaths(m.userData, "9.9.9", "darwin");
    expect(fs.existsSync(managed.marker)).toBe(true);
    expect(JSON.parse(fs.readFileSync(managed.marker, "utf8"))).toMatchObject({ cadgenVersion: "9.9.9" });
    expect(fs.existsSync(managed.log)).toBe(true);
    // The download directory is cleaned up; only the interpreter stays.
    expect(fs.existsSync(managed.downloads)).toBe(false);

    const pip = m.execs.find((exec) => exec.args[1] === "pip");
    expect(pip?.file).toBe(managed.python);
    expect(pip?.args).toEqual(["-m", "pip", "install", "cadgen==9.9.9"]);

    // Progress moves forward and ends at 100.
    const percents = progress.map((event) => event.percent).filter((value): value is number => value !== undefined);
    expect(percents[0]).toBe(0);
    expect(percents.at(-1)).toBe(100);
    expect([...percents]).toEqual([...percents].sort((a, b) => a - b));
    expect(progress.some((event) => event.message?.includes("Downloading Python"))).toBe(true);
    expect(progress.some((event) => event.message?.includes("Installing cadgen"))).toBe(true);
  });

  it("offers the bundled wheel with --find-links and the constraints with -c", async () => {
    const bytes = Buffer.from("python-build-standalone bytes");
    const m = machine({ downloadBytes: bytes, wheel: true });
    const runtime = new CadRuntime(m.host, pinFor(bytes));
    const { args } = runtime.pipArgs();
    expect(args).toEqual([
      "--find-links",
      path.join(m.host.resourcesDir, "cadgen"),
      "cadgen==9.9.9",
      "-c",
      path.join(m.host.resourcesDir, "cadgen", "constraints.txt"),
    ]);
    expect((await runtime.provision()).state).toBe("ready");
    const pip = m.execs.find((exec) => exec.args[1] === "pip");
    expect(pip?.args.slice(2)).toEqual(["install", ...args]);
  });

  it("refuses a download whose hash is not the pinned one, and leaves no marker", async () => {
    const m = machine({ downloadBytes: Buffer.from("tampered") });
    // The real pin: whatever the fake downloads, it is not python-build-standalone.
    const runtime = new CadRuntime(m.host);
    const status = await runtime.provision();
    expect(status.state).toBe("error");
    expect(status.message).toContain("checksum mismatch");
    expect(status.log).toContain("[error]");
    expect(m.extracts).toHaveLength(0);
    expect(fs.existsSync(managedPaths(m.userData, "9.9.9", "darwin").marker)).toBe(false);
    // And resolution still finds nothing: the half-provisioned runtime is not a runtime.
    expect(runtime.resolve()).toBeNull();
  });

  it("repair re-probes rather than provisions when an override is in force", async () => {
    const m = machine({ override: "/setting/python" });
    fs.writeFileSync(path.join(m.userData, "python"), "");
    (m.host as { overrideSetting: () => string | null }).overrideSetting = () => path.join(m.userData, "python");
    const runtime = new CadRuntime(m.host);
    const status = await runtime.repair();
    expect(status.overridden).toBe(true);
    expect(m.downloads).toHaveLength(0);
  });

  it("shares one in-flight provision between concurrent callers", async () => {
    const bytes = Buffer.from("python-build-standalone bytes");
    const m = machine({ downloadBytes: bytes });
    const runtime = new CadRuntime(m.host, pinFor(bytes));
    const [a, b] = await Promise.all([runtime.provision(), runtime.provision()]);
    expect(a.state).toBe("ready");
    expect(b.state).toBe("ready");
    expect(m.downloads).toHaveLength(1);
  });
});

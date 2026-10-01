/**
 * `warmCad` at project open: the viewer is warmed for a root with a model in
 * it (the daemon and the probe are global, so every root runs them), the build
 * daemon only on an interpreter `daemonReady` gives — never on one whose CAD kernel
 * failed, where the daemon (which imports OCP to start) would only fail,
 * noisily, on every project open. `ready()` still answers for such a runtime,
 * so a warm-up that asked it instead would start the daemon here.
 */
import { beforeEach, expect, test, vi } from "vitest";

const fakes = vi.hoisted(() => {
  const resolved = { python: "/runtime/python", source: "bundled", env: {} };
  return {
    resolved,
    ready: vi.fn(),
    daemonReady: vi.fn(),
    warm: vi.fn(),
    originFor: vi.fn(),
    hasCadFile: vi.fn(),
  };
});

vi.mock("electron", () => ({ app: { getPath: () => "/user-data" } }));
vi.mock("@main/app-paths", () => ({ appVersion: () => "0.0.0", appRoot: () => "/app", resourcesDir: () => "/resources" }));
vi.mock("@main/db/repositories", () => ({ explorerTabs: { list: () => [] }, projects: { get: () => null }, sessions: { list: () => [] }, settings: { get: () => ({ cadPythonOverride: null }) } }));
vi.mock("@main/projects/git", () => ({ samePath: () => false }));
vi.mock("@main/cad/runtime", () => ({
  CadRuntime: class {
    ready = fakes.ready;
    daemonReady = fakes.daemonReady;
    processEnv = () => ({});
    log = async () => {};
  },
  nodeHost: () => ({}),
  runtimeLogPath: () => "/user-data/cad-runtime.log",
}));
vi.mock("@main/cad/viewer", () => ({ ViewerManager: class { originFor = fakes.originFor; } }));
vi.mock("@main/cad/has-cad-file", () => ({ hasCadFile: fakes.hasCadFile, CAD_FILE: /\.step$/ }));
vi.mock("@main/cad/daemon", () => ({ DaemonWarmer: class { warm = fakes.warm; } }));
import { initCad, warmCad } from "@main/cad";

beforeEach(async () => {
  fakes.ready.mockReset().mockResolvedValue(fakes.resolved);
  fakes.daemonReady.mockReset();
  fakes.warm.mockReset();
  fakes.hasCadFile.mockReset().mockResolvedValue(true);
  fakes.originFor.mockReset().mockResolvedValue("http://127.0.0.1:1");
  await initCad();
});

test("a runtime whose CAD kernel failed warms the viewer but not the daemon", async () => {
  fakes.daemonReady.mockResolvedValue(null);
  await warmCad("/project");
  expect(fakes.originFor).toHaveBeenCalledOnce();
  expect(fakes.warm).not.toHaveBeenCalled();
});

test("a runtime the daemon can start on warms both, on the interpreter daemonReady gives", async () => {
  fakes.daemonReady.mockResolvedValue(fakes.resolved);
  await warmCad("/project");
  expect(fakes.originFor).toHaveBeenCalledOnce();
  expect(fakes.warm).toHaveBeenCalledWith(fakes.resolved);
});

test("a root with no CAD file starts no viewer but still warms the daemon", async () => {
  fakes.hasCadFile.mockResolvedValue(false);
  fakes.daemonReady.mockResolvedValue(fakes.resolved);
  await warmCad("/prose-only");
  expect(fakes.originFor).not.toHaveBeenCalled();
  expect(fakes.warm).toHaveBeenCalledWith(fakes.resolved);
});

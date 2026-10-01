/** CAD runtime, viewer backends and compilation warm-up. App integrations live beside this module. */
import { app } from "electron";
import path from "node:path";
import { appVersion, appRoot, resourcesDir } from "../app-paths";
import { sessions, settings } from "../db/repositories";
import * as git from "../projects/git";
import { DaemonWarmer } from "./daemon";
import { CadRuntime, nodeHost, runtimeLogPath } from "./runtime";
import { ViewerManager } from "./viewer";
let runtimeInstance: CadRuntime | null = null;
let viewersInstance: ViewerManager | null = null;
let daemonInstance: DaemonWarmer | null = null;
export function cadRuntime(): CadRuntime {
  if (!runtimeInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return runtimeInstance;
}

export function viewers(): ViewerManager {
  if (!viewersInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return viewersInstance;
}

export function sessionRuntimePath(): string[] {
  return runtimeInstance?.sessionPath() ?? [];
}

export function daemonWarmer(): DaemonWarmer {
  if (!daemonInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return daemonInstance;
}

/**
 * A project opened at `root`: start what its first CAD file will need. The
 * viewer's launch probes the runtime first (`import cadgen.viewer`, which
 * primes the interpreter's caches for every cadgen process after it), and
 * the daemon follows once the probe has said which interpreter runs. Nothing
 * here is awaited by the caller; `cad.viewerOrigin` shares the launch.
 *
 * Measured on the reference machine (scripts/perf-cad.mjs): the first STEP
 * open after launch paid 0.9 s for the probe and the viewer and 3.5 s for
 * the daemon's own start inside its compile; warmed at project open, both
 * are done before the click.
 */
export async function warmCad(root: string): Promise<void> {
  const viewer = viewers().originFor(root);
  const resolved = await cadRuntime().ready();
  if (resolved) {
    daemonWarmer().warm(resolved, root);
  }
  await viewer;
}

export async function initCad(): Promise<void> {
  const userData = app.getPath("userData");
  runtimeInstance = new CadRuntime(
    nodeHost({
      userData,
      appVersion: appVersion(),
      resourcesDir: resourcesDir(),
      appRoot: appRoot(),
      overrideSetting: () => settings.get().cadPythonOverride,
    }),
  );

  viewersInstance = new ViewerManager({
    runtime: () => runtimeInstance!.ready(),
    env: (resolved) => runtimeInstance!.processEnv(resolved),
    // The viewer's stderr and its launch failures go to the runtime log
    // beside the probe's, so one file answers "why is there no viewer".
    log: (line) => {
      console.info(`[viewer] ${line}`);
      void runtimeInstance!.log(`[viewer] ${line}`);
    },
  });

  daemonInstance = new DaemonWarmer({
    env: (resolved) => runtimeInstance!.processEnv(resolved),
    logFile: () => runtimeLogPath(userData),
    log: (line) => {
      console.info(`[daemon] ${line}`);
      void runtimeInstance!.log(`[daemon] ${line}`);
    },
  });

}
export function forgetCadSession(sessionId: string, worktreePath?: string | null): void {
  if (worktreePath && !sessions.list().some(other => other.id !== sessionId && git.samePath(other.cwd, worktreePath))) viewersInstance?.stop(path.resolve(worktreePath));
}
export async function shutdownCad(): Promise<void> { viewersInstance?.stopAll(); }

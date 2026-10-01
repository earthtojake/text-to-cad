/** CAD runtime, viewer backends and compilation warm-up. App integrations live beside this module. */
import { app } from "electron";
import path from "node:path";
import { appVersion, appRoot, resourcesDir } from "../app-paths";
import { explorerTabs, projects, sessions, settings } from "../db/repositories";
import * as git from "../projects/git";
import { DaemonWarmer } from "./daemon";
import { CAD_FILE, hasCadFile } from "./has-cad-file";
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
 * The key a root's viewer is launched and stopped by. `cad.viewerOrigin`
 * (the tab's root, from `rootOf` — the session's recorded spelling) and
 * `forgetCadSession` (the recorded `worktreePath`) both go through this, so
 * a stop always finds the instance its start made.
 */
export function viewerRoot(root: string): string {
  return path.resolve(root);
}

/**
 * A project opened at `root`: start what its first CAD file will need. The
 * viewer's launch probes the runtime first (`import cadgen.viewer`, which
 * primes the interpreter's caches for every cadgen process after it), and
 * the daemon follows once the probe has said which interpreter runs. Nothing
 * here is awaited by the caller; `cad.viewerOrigin` shares the launch.
 *
 * The viewer only for a root with a CAD file near its top (`hasCadFile`);
 * the probe and the daemon are global, once per run, so every bind runs them
 * (an empty project is the main flow, and its first build should not pay the
 * daemon's start).
 *
 * Measured on the reference machine (scripts/perf-cad.mjs): the first STEP
 * open after launch paid 0.9 s for the probe and the viewer and 3.5 s for
 * the daemon's own start inside its compile; warmed at project open, both
 * are done before the click.
 */
export async function warmCad(root: string): Promise<void> {
  // Every session bind asks. A root with no model in it would start a Python
  // viewer that idles until quit; its first CAD tab launches one through
  // `cad.viewerOrigin` instead. The daemon is not per root: it follows anyway.
  const viewer = hasCadFile(root).then((has) => (has ? viewers().originFor(viewerRoot(root)) : null));
  // Not on a runtime with a CAD kernel warning: the daemon imports OCP to
  // start (`CadRuntime.daemonReady` logs why, once).
  const resolved = await cadRuntime().daemonReady();
  if (resolved) {
    daemonWarmer().warm(resolved);
  }
  await viewer;
}

/**
 * The viewer roots that have a CAD tab open in a live session, read from the
 * persisted strips (the tab's own root, or its project's directory). The
 * viewer manager never evicts one of these to stay within its bound.
 */
export function openCadRoots(): string[] {
  const roots = new Set<string>();
  for (const session of sessions.list()) {
    if (session.archived) continue;
    for (const tab of explorerTabs.list(session.id)) {
      if (tab.kind !== "file" || !tab.path || !CAD_FILE.test(tab.path)) continue;
      const root = tab.root ?? projects.get(tab.projectId)?.path;
      if (root) roots.add(viewerRoot(root));
    }
  }
  return [...roots];
}

export async function initCad(): Promise<void> {
  const userData = app.getPath("userData");
  runtimeInstance = new CadRuntime(
    nodeHost({
      userData,
      appVersion: appVersion(),
      resourcesDir: resourcesDir(),
      appRoot: appRoot(),
      packaged: app.isPackaged,
      overrideSetting: () => settings.get().cadPythonOverride,
    }),
  );

  viewersInstance = new ViewerManager({
    runtime: () => runtimeInstance!.ready(),
    env: (resolved) => runtimeInstance!.processEnv(resolved),
    inUse: openCadRoots,
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
    cwd: () => userData,
    log: (line) => {
      console.info(`[daemon] ${line}`);
      void runtimeInstance!.log(`[daemon] ${line}`);
    },
  });

}
/**
 * A session's worktree viewer stops with its last open user; an archived
 * thread is not open (`sessionsUsing`), so it does not keep the viewer alive.
 */
export function forgetCadSession(sessionId: string, worktreePath?: string | null): void {
  if (worktreePath && git.sessionsUsing(sessions.list().filter(other => other.id !== sessionId), worktreePath).length === 0) viewersInstance?.stop(viewerRoot(worktreePath));
}
export async function shutdownCad(): Promise<void> { viewersInstance?.stopAll(); }

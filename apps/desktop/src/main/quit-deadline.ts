/**
 * A deadline on quitting.
 *
 * By `will-quit` everything this app owns is done: the database is closed,
 * the window has saved its geometry and run its unload, every child has its
 * signal and the probes are dead (`before-quit`, src/main/index.ts). What is
 * left is Chromium's own shutdown — and on macOS 26 with Electron 40, once a
 * window has held a WebGL context, that shutdown was measured at anywhere
 * from twelve seconds to two and a half minutes (the GPU and utility helpers
 * hang for ten to thirty seconds, then the browser process sits in a
 * CoreAnalytics XPC retry loop; `app.exit()` was slower still). Nothing in
 * that time is doing work for the user, and no timer of ours can fire during
 * it: the Node event loop is already stopped.
 *
 * So the deadline is kept by a process of its own — this Electron binary run
 * as Node, detached, which waits and then kills the app and the helpers it
 * still has (a utility process left to notice on its own took over thirty
 * seconds) if they are still there. A graceful exit that finishes first
 * (the common case without WebGL: about half a second) leaves the watchdog
 * nothing to do. Measured with the deadline: the process is gone within a
 * quarter second of the kill landing, and so are its helpers.
 */
import { spawn } from "node:child_process";

/** The quit deadline, including teardown and watchdog startup, within the two-second budget. */
export const QUIT_DEADLINE_MS = 1_200;

/**
 * The watchdog's whole program. Platform-specific in one place: on Windows
 * `taskkill /T` ends the tree; elsewhere the direct children are listed and
 * killed before the parent. Our own children are already gone by then; what
 * `pgrep -P` finds is Chromium's helpers.
 */
export function watchdogScript(pid: number, deadlineMs: number, platform: NodeJS.Platform = process.platform, startedAt = Date.now()): string {
  const kill =
    platform === "win32"
      ? `require("node:child_process").spawnSync("taskkill", ["/PID", "${pid}", "/T", "/F"], { stdio: "ignore" });`
      : `const cp = require("node:child_process");
let children = [];
try { children = cp.execFileSync("pgrep", ["-P", "${pid}"], { encoding: "utf8" }).trim().split(/\\s+/).filter(Boolean); } catch {}
for (const child of children) {
  if (Number(child) === process.pid) continue;
  try { process.kill(Number(child), "SIGKILL"); } catch {}
}
try { process.kill(${pid}, "SIGKILL"); } catch {}`;
  return `setTimeout(() => {
let alive = true;
try { process.kill(${pid}, 0); } catch { alive = false; }
if (alive) { ${kill} }
}, Math.max(0, ${startedAt + deadlineMs} - Date.now()));`;
}

export function armQuitDeadline(startedAt = Date.now(), pid: number = process.pid, deadlineMs: number = QUIT_DEADLINE_MS): void {
  try {
    // Arm only after will-quit, once state is saved. If teardown or launching
    // Electron-as-Node used the budget, the watchdog fires immediately.
    spawn(process.execPath, ["-e", watchdogScript(pid, deadlineMs, process.platform, startedAt)], {
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" },
    }).unref();
  } catch (error) {
    // Without a watchdog the app still quits, only slowly.
    console.error("[quit] could not arm the deadline", error);
  }
}

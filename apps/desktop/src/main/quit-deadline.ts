/**
 * A deadline on quitting.
 *
 * By the end of `before-quit` everything this app owns is done: the database is closed,
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

import { daemonPids } from "./cad/daemon";
import { isQuittingForUpdate } from "./quitting";

/** The quit deadline, including teardown and watchdog startup, within the two-second budget. */
export const QUIT_DEADLINE_MS = 1_200;

/**
 * How long the watchdog's one probe (`ps -axo pid=,ppid=,pgid=`: every process with its parent
 * and group) may take. The budget arithmetic is stated once, in
 * `tests/unit/main/quit-deadline.test.ts`, and raising this fails there. The timeout is generous
 * because starting a process on a loaded CI runner took longer than the 150 ms an earlier,
 * two-probe version allowed, and a probe that times out leaves every child alive. A probe that hangs is killed and treated as having
 * found nothing: only the app is killed.
 */
export const WATCHDOG_PROBE_TIMEOUT_MS = 400;

/**
 * The watchdog's whole program. Platform-specific in one place: on Windows
 * `taskkill /T` ends the tree; elsewhere the direct children are found and
 * killed before the parent. Our own children are already gone by then; what
 * the probe finds is Chromium's helpers.
 *
 * Every direct child is killed except the pids in `spare`: the shared warm
 * daemon (`daemonPids()`, src/main/cad/daemon.ts) outlives the app by design.
 * It is spared by identity, not by process group, because the app-owned
 * viewer is `detached` too (its own group, so its compile workers die with
 * it) and must not be spared with it. A child that leads a group of its own
 * is killed as a group (`kill(-pgid)`); Chromium's helpers, in the app's
 * group, are killed one by one. A viewer reused from another app run is not
 * a child of this process and is never seen here.
 *
 * One probe finds the children and their groups: `ps -axo pid=,ppid=,pgid=` lists every
 * process with its parent and group (BSD/macOS `ps` and Linux procps both take `-a -x -o`, and
 * an empty name after each field drops the header), the children are the rows whose ppid is the app's. It runs under a
 * timeout (`probeTimeoutMs`) so a hung `ps` cannot stall the final kill of the app: a probe that
 * fails or times out finds no children and only the app is killed. A probe that exits non-zero
 * but printed rows is read for those rows.
 *
 * Windows has no spare list: `taskkill /T` follows ParentProcessId, which `detached` does
 * not change, so when the deadline is reached the tree kill takes the warm daemon with
 * it and the next launch cold-starts it. (Sparing it would need a different mechanism; the
 * test "carries no spare list on Windows" pins the current behaviour so a change is deliberate.)
 *
 * Except when the quit is an update's (`tree` false): electron-updater has
 * just spawned the NSIS installer, or the new AppImage, as a child of this
 * process, and a tree kill would take it down mid-install. Then only the app
 * itself is killed; its helpers go with the browser process they serve.
 * Not on macOS: Squirrel's ShipIt is launched by launchd, not by the app, so
 * there is no installer in the tree to spare — only helpers to leave behind.
 */
export function watchdogScript(
  pid: number,
  deadlineMs: number,
  platform: NodeJS.Platform = process.platform,
  startedAt = Date.now(),
  tree = true,
  spare: readonly number[] = [],
  probeTimeoutMs: number = WATCHDOG_PROBE_TIMEOUT_MS,
): string {
  const kill =
    platform === "win32"
      ? `require("node:child_process").spawnSync("taskkill", ["/PID", "${pid}", ${tree ? `"/T", ` : ""}"/F"], { stdio: "ignore" });`
      : tree
        ? `const cp = require("node:child_process");
const probe = (file, args) => {
  try { return cp.execFileSync(file, args, { encoding: "utf8", timeout: ${Math.max(1, Math.floor(probeTimeoutMs))}, killSignal: "SIGKILL" }); }
  catch (error) { return error && error.code !== "ETIMEDOUT" && typeof error.stdout === "string" ? error.stdout : ""; }
};
const rows = probe("ps", ["-axo", "pid=,ppid=,pgid="]).trim().split("\\n")
  .map((line) => line.trim().split(/\\s+/).map(Number))
  .filter((row) => row.length === 3 && row.every(Number.isInteger));
const groups = new Map(rows.map(([member, , group]) => [member, group]));
const children = rows.filter(([, parent]) => parent === ${pid}).map(([member]) => String(member));
const spare = ${JSON.stringify(spare.filter(Number.isInteger))};
const own = groups.get(${pid});
for (const child of children) {
  const target = Number(child);
  if (target === process.pid || spare.includes(target)) continue;
  const group = groups.get(target);
  if (group !== undefined && group === target && group !== own) { try { process.kill(-group, "SIGKILL"); } catch {} }
  try { process.kill(target, "SIGKILL"); } catch {}
}
try { process.kill(${pid}, "SIGKILL"); } catch {}`
        : `try { process.kill(${pid}, "SIGKILL"); } catch {}`;
  return `setTimeout(() => {
let alive = true;
try { process.kill(${pid}, 0); } catch { alive = false; }
if (alive) { ${kill} }
}, Math.max(0, ${startedAt + deadlineMs} - Date.now()));`;
}

export function armQuitDeadline(
  startedAt = Date.now(),
  pid: number = process.pid,
  deadlineMs: number = QUIT_DEADLINE_MS,
  platform: NodeJS.Platform = process.platform,
  tree: boolean = !isQuittingForUpdate() || platform === "darwin",
  spare: readonly number[] = daemonPids(),
): void {
  try {
    // Armed once, once state is saved: at the end of before-quit (nothing cancels a
    // quit after its teardown; the database is closed). index.ts arms from will-quit
    // too, as the fallback if before-quit threw before reaching its `try`; its guard makes
    // that a no-op otherwise.
    // If teardown or launching Electron-as-Node used the budget, the watchdog
    // fires immediately.
    spawn(process.execPath, ["-e", watchdogScript(pid, deadlineMs, platform, startedAt, tree, spare)], {
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

import * as childProcess from "node:child_process";
import { once } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { runInNewContext } from "node:vm";

import { describe, expect, it, vi } from "vitest";

import { armQuitDeadline, watchdogScript } from "@main/quit-deadline";
import { markQuittingForUpdate } from "@main/quitting";

// The real spawn, observable: `armQuitDeadline` is checked by the script it
// hands the watchdog, and those two calls are answered by a stub.
vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof childProcess>();
  return { ...actual, spawn: vi.fn(actual.spawn) };
});
const { spawn } = childProcess;

/**
 * The watchdog is a script handed to `node -e`; the only way to know it does
 * what its comment says is to run it against a process and watch. A
 * process that exits on its own is left alone, one that is still there at
 * the deadline is killed along with its children.
 */
const alive = (pid: number) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

const runWatchdog = (pid: number, deadlineMs: number, spare: number[] = [], probeTimeoutMs?: number, env?: NodeJS.ProcessEnv) =>
  new Promise<{ code: number | null; signal: NodeJS.Signals | null }>((resolve) =>
    spawn(process.execPath, ["-e", watchdogScript(pid, deadlineMs, process.platform, Date.now(), true, spare, probeTimeoutMs)], { stdio: "ignore", env }).once("exit", (code, signal) =>
      resolve({ code, signal }),
    ),
  );

/** A directory that shadows `ps` on PATH for one watchdog run. */
const withStubPs = (body: string) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "quit-deadline-ps-"));
  fs.writeFileSync(path.join(dir, "ps"), `#!/bin/sh\n${body}\n`, { mode: 0o755 });
  return { env: { ...process.env, PATH: `${dir}${path.delimiter}${process.env.PATH}` }, dir };
};

/** The app's shape for the probe tests: an attached helper, and a detached viewer with a worker in its group. */
const launchApp = async () => {
  const target = spawn(process.execPath, ["-e", `
const { spawn } = require("node:child_process");
const worker = "require('node:child_process').spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' }).once('spawn', function () { process.send(this.pid); }); setInterval(() => {}, 1000)";
const launch = (detached, code) => new Promise((resolve) => {
  const child = spawn(process.execPath, ["-e", code], { detached, stdio: ["ignore", "ignore", "ignore", "ipc"] });
  child.once("message", (grandchild) => resolve({ pid: child.pid, grandchild }));
  child.unref();
});
Promise.all([launch(false, "process.send(0); setInterval(() => {}, 1000)"), launch(true, worker)])
  .then(([attached, viewer]) => process.send({ attached: attached.pid, viewer: viewer.pid, worker: viewer.grandchild }));
setInterval(() => {}, 1000);
`], { stdio: ["ignore", "ignore", "pipe", "ipc"] });
  const [ready] = await once(target, "message");
  const pids = ready as { attached: number; viewer: number; worker: number };
  const all = [target.pid!, pids.attached, pids.viewer, pids.worker];
  return { target, pids, all, cleanup: () => all.forEach((pid) => { try { process.kill(pid, "SIGKILL"); } catch { /* already gone */ } }) };
};

describe("the quit deadline's watchdog", () => {
  it("counts teardown and process startup against the original deadline", () => {
    const startedAt = 1_000;
    const script = watchdogScript(123, 1_200, "darwin", startedAt);
    const remaining: number[] = [];
    for (const now of [1_000, 1_700, 2_500]) {
      runInNewContext(script, {
        Date: { now: () => now },
        setTimeout: (_callback: () => void, delay: number) => remaining.push(delay),
      });
    }
    expect(remaining).toEqual([1_200, 500, 0]);
  });

  it("never signals itself while ending the target's remaining helpers", () => {
    const signaled: number[] = [];
    runInNewContext(watchdogScript(123, 0, "darwin"), {
      Date,
      process: { pid: 321, kill: (pid: number, signal?: string) => { if (signal) { signaled.push(pid); } } },
      require: () => ({ execFileSync: (file: string) => (file === "pgrep" ? "200\n321\n201\n" : "123 50\n200 50\n321 50\n201 50\n") }),
      setTimeout: (callback: () => void) => callback(),
    });
    expect(signaled).toEqual([200, 201, 123]);
  });

  it("spares the daemon by pid, and kills a detached child and its group like any other", async () => {
    // The app's shape: a Chromium helper (attached), the app-owned viewer (`detached`, its own group,
    // with a compile worker in it) and the warm daemon (`detached`, spared by pid). All are direct children.
    const target = spawn(process.execPath, ["-e", `
const { spawn } = require("node:child_process");
const worker = "require('node:child_process').spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' }).once('spawn', function () { process.send(this.pid); }); setInterval(() => {}, 1000)";
const launch = (detached, code) => new Promise((resolve) => {
  const child = spawn(process.execPath, ["-e", code], { detached, stdio: ["ignore", "ignore", "ignore", "ipc"] });
  child.once("message", (grandchild) => resolve({ pid: child.pid, grandchild }));
  child.unref();
});
const idle = "process.send(0); setInterval(() => {}, 1000)";
Promise.all([launch(false, idle), launch(true, worker), launch(true, idle)])
  .then(([attached, viewer, daemon]) => process.send({ attached: attached.pid, viewer: viewer.pid, worker: viewer.grandchild, daemon: daemon.pid }));
setInterval(() => {}, 1000);
`], { stdio: ["ignore", "ignore", "pipe", "ipc"] });
    let pids: { attached: number; viewer: number; worker: number; daemon: number } | undefined;
    try {
      const [ready] = await once(target, "message");
      pids = ready as typeof pids;
      await expect(runWatchdog(target.pid!, 0, [pids!.daemon])).resolves.toEqual({ code: 0, signal: null });
      await expect
        .poll(() => [target.pid!, pids!.attached, pids!.viewer, pids!.worker].filter(alive), { timeout: 5_000 })
        .toEqual([]);
      expect(alive(pids!.daemon), "the spared daemon is left running").toBe(true);
    } finally {
      for (const pid of [target.pid, pids?.attached, pids?.viewer, pids?.worker, pids?.daemon]) {
        if (pid) {
          try { process.kill(pid, "SIGKILL"); } catch { /* already gone */ }
        }
      }
    }
  });

  it("reads the rows of a ps variant that fails yet still printed them, so the viewer's group dies with it", async () => {
    // macOS `ps` exits 0 here; this stub stands in for a variant (unmeasured on Linux) that
    // reports a vanished pid as a failure while printing the rows it found.
    const stub = withStubPs('/bin/ps "$@"\nexit 1');
    const app = await launchApp();
    try {
      await expect(runWatchdog(app.target.pid!, 0, [], 2_000, stub.env)).resolves.toEqual({ code: 0, signal: null });
      // The worker is in the viewer's own group: only a kill of that group (known from ps's rows) ends it.
      await expect.poll(() => app.all.filter(alive), { timeout: 5_000 }).toEqual([]);
    } finally {
      app.cleanup();
      fs.rmSync(stub.dir, { recursive: true, force: true });
    }
  });

  it("kills the app at the deadline even when ps hangs", async () => {
    const stub = withStubPs("exec sleep 30");
    const app = await launchApp();
    const started = Date.now();
    try {
      await expect(runWatchdog(app.target.pid!, 0, [], 150, stub.env)).resolves.toEqual({ code: 0, signal: null });
      // The probe was cut off after its timeout, not waited out: the app is dead long before `sleep` ends.
      expect(Date.now() - started).toBeLessThan(10_000);
      expect(alive(app.target.pid!)).toBe(false);
      // With no groups known, the unspared children are killed singly (the worker in the viewer's group is not reached).
      await expect.poll(() => [app.pids.attached, app.pids.viewer].filter(alive), { timeout: 5_000 }).toEqual([]);
    } finally {
      app.cleanup();
      fs.rmSync(stub.dir, { recursive: true, force: true });
    }
  });

  it("a target-owned watchdog kills the target and helpers without killing itself first", async () => {
    const target = spawn(process.execPath, ["-e", `
const { spawn } = require("node:child_process");
const launch = () => new Promise((resolve) => {
  const child = spawn(process.execPath, ["-e", "process.send(process.pid); setInterval(() => {}, 1000)"], {
    stdio: ["ignore", "ignore", "ignore", "ipc"],
  });
  child.once("message", resolve);
});
Promise.all([launch(), launch()]).then((children) => process.send({ children }));
process.once("message", (script) => {
  const watchdog = spawn(process.execPath, ["-e", script], { detached: true, stdio: "ignore" });
  watchdog.unref();
  process.send({ watchdog: watchdog.pid });
});
setInterval(() => {}, 1000);
`], { stdio: ["ignore", "ignore", "pipe", "ipc"] });
    const children: number[] = [];
    let watchdog: number | undefined;
    try {
      const [ready] = await once(target, "message");
      children.push(...(ready as { children: number[] }).children);
      expect(children).toHaveLength(2);
      const armed = once(target, "message");
      target.send(watchdogScript(target.pid!, 100));
      const [launched] = await armed;
      watchdog = (launched as { watchdog: number }).watchdog;
      await expect.poll(() => [target.pid!, ...children].filter(alive), { timeout: 5_000 }).toEqual([]);
    } finally {
      for (const pid of [target.pid, watchdog, ...children]) {
        if (pid) {
          try { process.kill(pid, "SIGKILL"); } catch { /* already gone */ }
        }
      }
    }
  });

  it("leaves a process that exited on its own alone", async () => {
    const target = spawn(process.execPath, ["-e", "process.exit(0)"], { stdio: "ignore" });
    await new Promise((resolve) => target.once("exit", resolve));
    // The watchdog must not throw at a pid that is gone (or reused).
    await expect(runWatchdog(target.pid!, 50)).resolves.toEqual({ code: 0, signal: null });
    // And it sends nothing: the liveness probe fails, so no kill and no child scan.
    const signaled: [number, string][] = [];
    const scanned = vi.fn(() => "");
    runInNewContext(watchdogScript(target.pid!, 0, "darwin"), {
      Date,
      process: {
        pid: 321,
        kill: (pid: number, signal?: string | number) => {
          if (signal === 0) throw Object.assign(new Error("ESRCH"), { code: "ESRCH" });
          signaled.push([pid, String(signal)]);
        },
      },
      require: () => ({ execFileSync: scanned }),
      setTimeout: (callback: () => void) => callback(),
    });
    expect(signaled).toEqual([]);
    expect(scanned).not.toHaveBeenCalled();
  });

  it("carries no spare list on Windows, where the tree kill takes the warm daemon with it", () => {
    // `taskkill /T` follows ParentProcessId through `detached`. Flip this deliberately, together
    // with the README's "Quitting" section, if a Windows spare mechanism is ever built.
    const script = watchdogScript(123, 0, "win32", Date.now(), true, [777, 888]);
    expect(script).not.toMatch(/777|888|spare/);
    expect(script).toContain('"/T"');
  });

  it("after before-quit-for-update, kills only the app, never the installer it spawned", () => {
    // posix: no `pgrep -P` scan, so the relaunched AppImage (a child) lives.
    const signaled: number[] = [];
    const scanned = vi.fn(() => "200\n");
    runInNewContext(watchdogScript(123, 0, "linux", Date.now(), false), {
      Date,
      process: { pid: 321, kill: (pid: number, signal?: string) => { if (signal) { signaled.push(pid); } } },
      require: () => ({ execFileSync: scanned }),
      setTimeout: (callback: () => void) => callback(),
    });
    expect(scanned).not.toHaveBeenCalled();
    expect(signaled).toEqual([123]);

    // win32: `taskkill` without `/T`, so the NSIS installer (a child) lives.
    const taskkill = (tree: boolean) => {
      const calls: string[][] = [];
      runInNewContext(watchdogScript(123, 0, "win32", Date.now(), tree), {
        Date,
        process: { pid: 321, kill: () => true },
        require: () => ({ spawnSync: (_file: string, args: string[]) => calls.push(args) }),
        setTimeout: (callback: () => void) => callback(),
      });
      return calls;
    };
    expect(taskkill(true)).toEqual([["/PID", "123", "/T", "/F"]]);
    expect(taskkill(false)).toEqual([["/PID", "123", "/F"]]);

    // And the quit an update starts is what arms that script.
    const spawned = vi.mocked(spawn);
    const armed = (platform: NodeJS.Platform) => {
      spawned.mockImplementationOnce((() => ({ unref: () => undefined })) as never);
      armQuitDeadline(0, 4242, 0, platform);
      return String(spawned.mock.calls.at(-1)![1]![1]);
    };
    expect(armed("linux")).toContain("pgrep");
    // The app hands the watchdog the daemon's pid (src/main/cad/daemon.ts) to spare.
    spawned.mockImplementationOnce((() => ({ unref: () => undefined })) as never);
    armQuitDeadline(0, 4242, 0, "linux", true, [777]);
    expect(String(spawned.mock.calls.at(-1)![1]![1])).toContain("[777]");
    expect(armed("win32")).toContain('"/T"');
    markQuittingForUpdate();
    expect(armed("linux")).not.toContain("pgrep");
    expect(armed("win32")).not.toContain('"/T"');
    // Except on macOS: Squirrel's ShipIt is launched by launchd, not as a child of the app, so
    // the helpers still go — sparing them spares nothing but a utility process that outlives us.
    expect(armed("darwin")).toContain("pgrep");
  });
});

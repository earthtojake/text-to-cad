import { spawn } from "node:child_process";
import { once } from "node:events";
import { runInNewContext } from "node:vm";

import { describe, expect, it } from "vitest";

import { watchdogScript } from "@main/quit-deadline";

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

const runWatchdog = (pid: number, deadlineMs: number) =>
  new Promise<void>((resolve) => spawn(process.execPath, ["-e", watchdogScript(pid, deadlineMs)], { stdio: "ignore" }).once("exit", () => resolve()));

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
      require: () => ({ execFileSync: () => "200\n321\n201\n" }),
      setTimeout: (callback: () => void) => callback(),
    });
    expect(signaled).toEqual([200, 201, 123]);
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
    await runWatchdog(target.pid!, 50);
  });
});

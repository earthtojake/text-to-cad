import { execFileSync, spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

import { describe, expect, it } from "vitest";

import { watchdogScript } from "@main/quit-deadline";

/**
 * The watchdog is a script handed to `node -e`; the only way to know it does
 * what its comment says is to run it against a process and watch. A
 * process that exits on its own is left alone, one that is still there at
 * the deadline is killed along with its children.
 */
const sleeper = (children = 0) =>
  spawn(
    process.execPath,
    [
      "-e",
      `for (let i = 0; i < ${children}; i += 1) require("node:child_process").spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
setInterval(() => {}, 1000)`,
    ],
    { stdio: "ignore" },
  );

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
  it("kills a process still there at the deadline, and its children", async () => {
    const target = sleeper(2);
    await sleep(300);
    const children = childrenOf(target.pid!);
    expect(children).toHaveLength(2);
    await runWatchdog(target.pid!, 100);
    await sleep(100);
    expect(alive(target.pid!)).toBe(false);
    for (const child of children) {
      expect(alive(child)).toBe(false);
    }
  });

  it("leaves a process that exited on its own alone", async () => {
    const target = spawn(process.execPath, ["-e", "process.exit(0)"], { stdio: "ignore" });
    await new Promise((resolve) => target.once("exit", resolve));
    // The watchdog must not throw at a pid that is gone (or reused).
    await runWatchdog(target.pid!, 50);
  });
});

function childrenOf(pid: number): number[] {
  try {
    return execFileSync("pgrep", ["-P", String(pid)], { encoding: "utf8" }).trim().split(/\s+/).filter(Boolean).map(Number);
  } catch {
    return [];
  }
}

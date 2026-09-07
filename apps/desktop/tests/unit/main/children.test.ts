import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

import { execa } from "execa";
import { afterEach, describe, expect, it } from "vitest";

import { endTrackedChildren, killTrackedChildren, trackChild, trackedChildren } from "@main/children";

/**
 * The registry behind a two-second quit. Real children, because what is
 * being tested is that a signal lands and a pipe is dropped, and a fake
 * would only prove the bookkeeping. Both shapes the app spawns are here:
 * Node's `ChildProcess` and execa's promise-with-a-pid.
 */
const sleepScript = "setInterval(() => {}, 1000)";
const sleeper = () => spawn(process.execPath, ["-e", sleepScript], { stdio: ["pipe", "pipe", "pipe"] });

const exited = (child: ReturnType<typeof spawn>) =>
  new Promise<NodeJS.Signals | number | null>((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve(child.signalCode ?? child.exitCode);
      return;
    }
    child.once("exit", (code, signal) => resolve(signal ?? code));
  });

afterEach(() => {
  killTrackedChildren();
});

describe("tracked children", () => {
  it("forgets a child once it has exited", async () => {
    const child = trackChild(spawn(process.execPath, ["-e", "process.exit(0)"]), "probe");
    expect(trackedChildren().map((entry) => entry.pid)).toContain(child.pid);
    await exited(child);
    // The exit listener runs after the event; give it the tick.
    await sleep(10);
    expect(trackedChildren()).toHaveLength(0);
  });

  it("before-quit kills probes and leaves services to their owners", async () => {
    const probe = trackChild(sleeper(), "probe");
    const service = trackChild(sleeper(), "service");
    endTrackedChildren();
    expect(await exited(probe)).toBe("SIGKILL");
    expect(service.exitCode).toBeNull();
    expect(service.signalCode).toBeNull();
    // Detached: its pipes are gone, so nothing waits on it.
    expect(service.stdout?.destroyed).toBe(true);
  });

  it("will-quit kills whatever is left", async () => {
    const service = trackChild(sleeper(), "service");
    killTrackedChildren();
    expect(await exited(service)).toBe("SIGKILL");
    expect(trackedChildren()).toHaveLength(0);
  });

  it("tracks an execa subprocess, which is a promise rather than an emitter", async () => {
    const subprocess = trackChild(execa(process.execPath, ["-e", sleepScript], { reject: false }), "probe");
    expect(trackedChildren().map((entry) => entry.pid)).toContain(subprocess.pid);
    endTrackedChildren();
    const result = await subprocess;
    expect(result.signal).toBe("SIGKILL");
    await sleep(10);
    expect(trackedChildren()).toHaveLength(0);
  });

  it("does not change what an execa call answers", async () => {
    const result = await trackChild(execa("git", ["--version"], { reject: false }), "probe");
    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain("git version");
  });
});

import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";

import { execa } from "execa";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    // The exit listener runs after the event.
    await vi.waitFor(() => expect(trackedChildren()).toHaveLength(0));
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

  /** A child that has installed its SIGTERM handler, which is what git's lock cleanup is. */
  const writer = async (onTerm: string) => {
    const child = trackChild(
      spawn(process.execPath, ["-e", `process.on("SIGTERM", () => { ${onTerm} });\nconsole.log("ready");\nsetInterval(() => {}, 1000);`], {
        stdio: ["pipe", "pipe", "pipe"],
      }),
      "write",
    );
    await once(child.stdout!, "data");
    return child;
  };

  it("before-quit asks a write to stop with SIGTERM, so it can drop its lock, and lets go of its pipes", async () => {
    // Exits 7 from its handler: a SIGKILL would end it by signal instead.
    const write = await writer("process.exit(7)");
    endTrackedChildren();
    expect(await exited(write)).toBe(7);
    expect(write.stdout?.destroyed).toBe(true);
  });

  it("will-quit kills a write that ignored SIGTERM", async () => {
    const write = await writer("");
    endTrackedChildren();
    expect(write.exitCode).toBeNull();
    expect(write.signalCode).toBeNull();
    killTrackedChildren();
    expect(await exited(write)).toBe("SIGKILL");
  });

  it("will-quit kills whatever is left", async () => {
    const service = trackChild(sleeper(), "service");
    killTrackedChildren();
    expect(await exited(service)).toBe("SIGKILL");
    expect(trackedChildren()).toHaveLength(0);
  });

  it.skipIf(process.platform === "win32")("ends an owned worker when its service exits first, preserving a separate daemon session", async () => {
    const { service, worker, daemon } = await serviceTree();
    try {
      // All three handlers are ready. The worker deliberately ignores this
      // signal; the service exits before will-quit gets to its registry.
      process.kill(-service.pid!, "SIGTERM");
      expect(await exited(service)).toBe(0);
      await expect.poll(() => running(worker), { timeout: 5_000 }).toBe(false);
      expect(trackedChildren().map((entry) => entry.pid)).not.toContain(service.pid);
      killTrackedChildren();
      expect(running(daemon)).toBe(true);
    } finally {
      cleanTree(service, worker, daemon);
    }
  });

  it.skipIf(process.platform === "win32")("will-quit ends every member of an owned service group", async () => {
    const { service, worker, daemon } = await serviceTree();
    try {
      killTrackedChildren();
      expect(await exited(service)).toBe("SIGKILL");
      await expect.poll(() => running(worker), { timeout: 5_000 }).toBe(false);
      expect(running(daemon)).toBe(true);
    } finally {
      cleanTree(service, worker, daemon);
    }
  });

  it("tracks an execa subprocess, which is a promise rather than an emitter", async () => {
    const subprocess = trackChild(execa(process.execPath, ["-e", sleepScript], { reject: false }), "probe");
    expect(trackedChildren().map((entry) => entry.pid)).toContain(subprocess.pid);
    endTrackedChildren();
    const result = await subprocess;
    expect(result.signal).toBe("SIGKILL");
    await vi.waitFor(() => expect(trackedChildren()).toHaveLength(0));
  });

  it("does not change what an execa call answers", async () => {
    const result = await trackChild(execa("git", ["--version"], { reject: false }), "probe");
    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain("git version");
  });
});

/** Real group membership, with IPC acknowledgments instead of startup sleeps. */
async function serviceTree() {
  const workerScript = `process.on("SIGTERM", () => {});
process.send(process.pid);
setInterval(() => {}, 1000);`;
  const service = trackChild(spawn(process.execPath, ["-e", `
const { spawn } = require("node:child_process");
process.on("SIGTERM", () => process.exit(0));
const launch = (detached) => new Promise((resolve) => {
  const child = spawn(process.execPath, ["-e", ${JSON.stringify(workerScript)}], {
    detached, stdio: ["ignore", "ignore", "ignore", "ipc"],
  });
  child.once("message", resolve);
});
Promise.all([launch(false), launch(true)]).then(([worker, daemon]) => process.send({ worker, daemon }));
setInterval(() => {}, 1000);
`], { detached: true, stdio: ["ignore", "ignore", "pipe", "ipc"] }), "service", { ownedProcessGroup: true });
  const [message] = await once(service, "message");
  const { worker, daemon } = message as { worker: number; daemon: number };
  expect(running(worker)).toBe(true);
  expect(running(daemon)).toBe(true);
  return { service, worker, daemon };
}

function running(pid: number): boolean {
  try {
    // An orphan can briefly await its reaper as a zombie; it has already
    // exited and cannot perform work. Keep the actual state in diagnostics.
    const state = execFileSync("ps", ["-o", "stat=", "-p", String(pid)], { encoding: "utf8" }).trim();
    return state !== "" && !state.startsWith("Z");
  } catch {
    return false;
  }
}

function cleanTree(service: ReturnType<typeof spawn>, ...pids: number[]): void {
  for (const pid of [service.pid, ...pids]) {
    if (pid) {
      try { process.kill(pid, "SIGKILL"); } catch { /* already gone */ }
    }
  }
}

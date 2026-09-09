import { describe, expect, it } from "vitest";

import { spawnProcessTerminal } from "@main/acp/process-backend";
import { TerminalManager, type SpawnTerminal, type TerminalProcess } from "@main/acp/terminals";

/** A process the test drives by hand. */
type Handle = {
  data: (s: string) => void;
  exit: (e: { exitCode: number | null; signal: string | null }) => void;
  killed: string[];
};

function fakeSpawn() {
  const handles: Handle[] = [];
  const spawn: SpawnTerminal = () => {
    const handle: Handle = { data: () => {}, exit: () => {}, killed: [] };
    handles.push(handle);
    const process: TerminalProcess = {
      pid: handles.length,
      onData: (listener) => {
        handle.data = listener;
      },
      onExit: (listener) => {
        handle.exit = listener;
      },
      write: () => {},
      kill: (signal) => {
        handle.killed.push(signal ?? "SIGTERM");
      },
    };
    return process;
  };
  return { spawn, handles };
}

describe("TerminalManager", () => {
  it("buffers output, reports exit, and forwards chunks to the listener", async () => {
    const { spawn, handles } = fakeSpawn();
    const seen: string[] = [];
    const manager = new TerminalManager(spawn, (_id, data) => seen.push(data));
    const id = manager.create({ command: "x", cwd: "/", baseEnv: {} });
    handles[0]!.data("hello ");
    handles[0]!.data("world");
    expect(manager.output(id)).toEqual({ output: "hello world", truncated: false, exitStatus: null });
    handles[0]!.exit({ exitCode: 0, signal: null });
    expect(await manager.waitForExit(id)).toEqual({ exitCode: 0, signal: null });
    expect(manager.output(id).exitStatus).toEqual({ exitCode: 0, signal: null });
    expect(seen).toEqual(["hello ", "world", ""]);
  });

  it("truncates from the front at the byte limit, on a character boundary", () => {
    const { spawn, handles } = fakeSpawn();
    const manager = new TerminalManager(spawn);
    const id = manager.create({ command: "x", cwd: "/", baseEnv: {}, outputByteLimit: 6 });
    // "é" is two bytes; the last 6 bytes of "abcdéfghij" start on its
    // continuation byte, which must be skipped.
    handles[0]!.data("abcdéfghij");
    const { output, truncated } = manager.output(id);
    expect(truncated).toBe(true);
    expect(Buffer.byteLength(output)).toBeLessThanOrEqual(6);
    expect(output).toBe("fghij");
  });

  it("kills a running process on kill and on release, and forgets it on release", () => {
    const { spawn, handles } = fakeSpawn();
    const manager = new TerminalManager(spawn);
    const id = manager.create({ command: "x", cwd: "/", baseEnv: {} });
    manager.kill(id);
    expect(handles[0]!.killed).toEqual(["SIGTERM"]);
    manager.release(id);
    expect(handles[0]!.killed).toEqual(["SIGTERM", "SIGTERM"]);
    expect(manager.has(id)).toBe(false);
    expect(() => manager.output(id)).toThrow(/unknown terminal/);
  });

  it("does not signal a process that already exited", () => {
    const { spawn, handles } = fakeSpawn();
    const manager = new TerminalManager(spawn);
    const id = manager.create({ command: "x", cwd: "/", baseEnv: {} });
    handles[0]!.exit({ exitCode: 1, signal: null });
    manager.release(id);
    expect(handles[0]!.killed).toEqual([]);
  });

  it("merges the agent's env entries over the base environment", () => {
    let seenEnv: Record<string, string> = {};
    const spawn: SpawnTerminal = ({ env }) => {
      seenEnv = env;
      return fakeSpawn().spawn({ command: "x", args: [], cwd: "/", env });
    };
    const manager = new TerminalManager(spawn);
    manager.create({ command: "x", cwd: "/", baseEnv: { PATH: "/bin", A: "1" }, env: [{ name: "A", value: "2" }] });
    expect(seenEnv).toEqual({ PATH: "/bin", A: "2" });
  });
});

describe("the child_process backend", () => {
  it("runs a real command, streams its output, and reports the exit code", async () => {
    const manager = new TerminalManager(spawnProcessTerminal);
    const id = manager.create({
      command: process.execPath,
      args: ["-e", "process.stdout.write('out'); process.stderr.write('err'); process.exit(3)"],
      cwd: process.cwd(),
      baseEnv: { PATH: process.env.PATH ?? "" },
    });
    const exit = await manager.waitForExit(id);
    expect(exit.exitCode).toBe(3);
    const { output } = manager.output(id);
    expect(output).toContain("out");
    expect(output).toContain("err");
    manager.release(id);
  });
});

import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

import { describe, expect, it } from "vitest";

import { VIEWER_ARGS, ViewerManager, originOf, parseLaunchLine, type ViewerChild } from "@main/cad/viewer";

/**
 * A fake `cadgen viewer`: prints what it is told on stdout, exits when asked.
 * The manager only ever sees the launcher's stdout contract and the exit
 * event, which is exactly what this reproduces.
 */
class FakeChild extends EventEmitter implements ViewerChild {
  pid = 4242;
  stdout = new PassThrough();
  stderr = new PassThrough();
  killed = false;
  kill() {
    this.killed = true;
    this.exit(null, "SIGTERM");
    return true;
  }
  say(line: string) {
    this.stdout.write(`${line}\n`);
  }
  exit(code: number | null, signal: NodeJS.Signals | null = null) {
    this.emit("exit", code, signal);
  }
}

function manager(options: { runtime?: boolean; probe?: () => Promise<boolean> } = {}) {
  const children: Array<{ child: FakeChild; python: string; args: string[]; cwd: string; env: Record<string, string> }> = [];
  const delays: number[] = [];
  const logs: string[] = [];
  const viewers = new ViewerManager({
    runtime: async () => (options.runtime === false ? null : { python: "/py", source: "override", env: { PYTHONPATH: "/src" } }),
    env: (resolved) => ({ ...resolved.env, HOME: "/home" }),
    spawn: (python, args, spawnOptions) => {
      const child = new FakeChild();
      children.push({ child, python, args, cwd: spawnOptions.cwd, env: spawnOptions.env });
      return child;
    },
    probe: options.probe ?? (async () => true),
    delay: async (ms) => {
      delays.push(ms);
    },
    log: (line) => logs.push(line),
  });
  return { viewers, children, delays, logs };
}

describe("parseLaunchLine", () => {
  it("reads the launcher's JSON line and ignores narration", () => {
    expect(parseLaunchLine('{"url":"http://127.0.0.1:3245/","port":3245,"action":"started"}')).toEqual({
      url: "http://127.0.0.1:3245/",
      port: 3245,
      action: "started",
    });
    expect(parseLaunchLine("Starting CAD Viewer API at http://127.0.0.1:3245/")).toBeNull();
    expect(parseLaunchLine('{"something":"else"}')).toBeNull();
    expect(parseLaunchLine("{not json")).toBeNull();
  });

  it("strips the trailing slash for the origin", () => {
    expect(originOf("http://127.0.0.1:3245/")).toBe("http://127.0.0.1:3245");
  });
});

describe("ViewerManager", () => {
  it("spawns python -m cadgen.viewer --api-only in the project root and answers the origin", async () => {
    const m = manager();
    const pending = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(1);
    const [launch] = m.children;
    expect(launch!.python).toBe("/py");
    expect(launch!.args).toEqual(VIEWER_ARGS);
    expect(launch!.args).toContain("--api-only");
    expect(launch!.args).toContain("--json");
    expect(launch!.cwd).toBe("/proj");
    expect(launch!.env.PYTHONPATH).toBe("/src");
    launch!.child.say("Starting CAD Viewer API at http://127.0.0.1:3250/ (serving /proj)");
    launch!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    expect(await pending).toEqual({ origin: "http://127.0.0.1:3250" });
    expect(m.viewers.list()).toEqual([{ root: "/proj", origin: "http://127.0.0.1:3250", reused: false, pid: 4242 }]);
  });

  it("answers runtime-not-ready without spawning when there is no interpreter", async () => {
    const m = manager({ runtime: false });
    expect(await m.viewers.originFor("/proj")).toEqual({ origin: null, reason: "runtime-not-ready" });
    expect(m.children).toHaveLength(0);
  });

  it("shares one launch between concurrent askers and reuses it afterwards", async () => {
    const m = manager();
    const a = m.viewers.originFor("/proj");
    const b = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(1);
    m.children[0]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    expect(await a).toEqual({ origin: "http://127.0.0.1:3250" });
    expect(await b).toEqual({ origin: "http://127.0.0.1:3250" });
    expect(await m.viewers.originFor("/proj")).toEqual({ origin: "http://127.0.0.1:3250" });
    expect(m.children).toHaveLength(1);
  });

  it("answers viewer-failed when the launcher exits before announcing", async () => {
    const m = manager();
    const pending = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    m.children[0]!.child.stderr.write("No built CAD Viewer client found\n");
    m.children[0]!.child.exit(1);
    expect(await pending).toEqual({ origin: null, reason: "viewer-failed" });
    expect(m.logs.some((line) => line.includes("No built CAD Viewer client found"))).toBe(true);
  });

  it("never kills a reused instance, and probes it before handing it out again", async () => {
    let alive = true;
    const m = manager({ probe: async () => alive });
    const pending = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    m.children[0]!.child.say('{"url":"http://127.0.0.1:3245/","port":3245,"action":"reused"}');
    expect(await pending).toEqual({ origin: "http://127.0.0.1:3245" });
    // The launcher exits after a reuse; that is not a crash and starts nothing.
    m.children[0]!.child.exit(0);
    expect(m.viewers.list()).toEqual([{ root: "/proj", origin: "http://127.0.0.1:3245", reused: true, pid: undefined }]);
    expect(m.delays).toHaveLength(0);

    // Alive: handed out without a launch.
    expect(await m.viewers.originFor("/proj")).toEqual({ origin: "http://127.0.0.1:3245" });
    expect(m.children).toHaveLength(1);

    // Stopping forgets it and kills nothing.
    m.viewers.stop("/proj");
    expect(m.children[0]!.child.killed).toBe(false);
    expect(m.viewers.list()).toEqual([]);

    // Gone: the next ask launches again (reuse-or-start).
    alive = false;
    const again = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(2);
    m.children[1]!.child.say('{"url":"http://127.0.0.1:3246/","port":3246,"action":"started"}');
    expect(await again).toEqual({ origin: "http://127.0.0.1:3246" });
  });

  it("restarts a crashed instance with backoff, and stops restarting once stopped", async () => {
    const m = manager();
    const pending = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    m.children[0]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    await pending;

    m.children[0]!.child.exit(1);
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.delays).toEqual([1000]);
    expect(m.children).toHaveLength(2);
    m.children[1]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    await new Promise((resolve) => setImmediate(resolve));
    expect(await m.viewers.originFor("/proj")).toEqual({ origin: "http://127.0.0.1:3250" });

    m.children[1]!.child.exit(1);
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.delays).toEqual([1000, 2000]);
    expect(m.children).toHaveLength(3);

    // A stop while the restart is up: kills ours, restarts nothing.
    m.children[2]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    await new Promise((resolve) => setImmediate(resolve));
    m.viewers.stop("/proj");
    expect(m.children[2]!.child.killed).toBe(true);
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(3);
    expect(m.viewers.list()).toEqual([]);
  });

  it("stopAll kills every instance it started", async () => {
    const m = manager();
    const a = m.viewers.originFor("/a");
    const b = m.viewers.originFor("/b");
    await new Promise((resolve) => setImmediate(resolve));
    m.children[0]!.child.say('{"url":"http://127.0.0.1:1/","port":1,"action":"started"}');
    m.children[1]!.child.say('{"url":"http://127.0.0.1:2/","port":2,"action":"started"}');
    await Promise.all([a, b]);
    m.viewers.stopAll();
    expect(m.children.every((entry) => entry.child.killed)).toBe(true);
    expect(m.viewers.list()).toEqual([]);
  });
});

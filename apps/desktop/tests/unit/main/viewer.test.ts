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

function manager(options: { now?: () => number; inUse?: () => string[]; maxLive?: number; runtime?: boolean; gate?: Promise<void>; probe?: () => Promise<boolean>; delay?: () => Promise<void> } = {}) {
  const children: Array<{ child: FakeChild; python: string; args: string[]; cwd: string; env: Record<string, string> }> = [];
  const delays: number[] = [];
  const logs: string[] = [];
  const viewers = new ViewerManager({
    runtime: async () => (await options.gate, options.runtime === false ? null : { python: "/py", source: "override", env: { PYTHONPATH: "/src" } }),
    env: (resolved) => ({ ...resolved.env, HOME: "/home" }),
    spawn: (python, args, spawnOptions) => {
      const child = new FakeChild();
      children.push({ child, python, args, cwd: spawnOptions.cwd, env: spawnOptions.env });
      return child;
    },
    probe: options.probe ?? (async () => true),
    delay: async (ms) => {
      delays.push(ms);
      await options.delay?.();
    },
    log: (line) => logs.push(line),
    ...(options.inUse ? { inUse: options.inUse } : {}),
    ...(options.now ? { now: options.now } : {}),
    ...(options.maxLive ? { maxLive: options.maxLive } : {}),
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
    expect(await pending).toMatchObject({ origin: null, reason: "viewer-failed", message: expect.stringContaining("exited") });
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

  it("a stop during a crash's restart delay cancels the restart, even with no entry left", async () => {
    for (const halt of ["stop", "stopAll"] as const) {
      let release!: () => void;
      const gate = new Promise<void>((resolve) => (release = resolve));
      const m = manager({ delay: () => gate });
      const pending = m.viewers.originFor("/proj");
      await new Promise((resolve) => setImmediate(resolve));
      m.children[0]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
      await pending;

      m.children[0]!.child.exit(1);
      await new Promise((resolve) => setImmediate(resolve));
      expect(m.delays).toEqual([1000]);
      if (halt === "stop") m.viewers.stop("/proj");
      else m.viewers.stopAll();
      release();
      await new Promise((resolve) => setImmediate(resolve));
      expect(m.children).toHaveLength(1);
      expect(m.viewers.list()).toEqual([]);

      // Asked for again afterwards, it launches as usual.
      const again = m.viewers.originFor("/proj");
      await new Promise((resolve) => setImmediate(resolve));
      expect(m.children).toHaveLength(2);
      m.children[1]!.child.say('{"url":"http://127.0.0.1:3251/","port":3251,"action":"started"}');
      expect(await again).toEqual({ origin: "http://127.0.0.1:3251" });
    }
  });

  it("a stop while a restart is launching kills it when it announces, and does not retry", async () => {
    const m = manager();
    const pending = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    m.children[0]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    await pending;

    m.children[0]!.child.exit(1);
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(2);
    m.viewers.stop("/proj");
    m.children[1]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children[1]!.child.killed).toBe(true);
    expect(m.children).toHaveLength(2);
    expect(m.delays).toEqual([1000]);
    expect(m.viewers.list()).toEqual([]);
  });

  it("a stop during the first launch kills it when it announces, and keeps nothing", async () => {
    // A session deleted while its viewer is still coming up.
    const m = manager();
    const pending = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    m.viewers.stop("/proj");
    m.children[0]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    expect(await pending).toMatchObject({ origin: null, reason: "viewer-failed" });
    expect(m.children[0]!.child.killed).toBe(true);
    expect(m.viewers.list()).toEqual([]);
    expect(m.children).toHaveLength(1);
  });

  it("counts crashes in a row: an instance that stayed up is forgiven, a crash loop is given up on", async () => {
    let clock = 0;
    const m = manager({ now: () => clock });
    const settle = () => new Promise((resolve) => setImmediate(resolve));
    const announce = (index: number) => m.children[index]!.child.say('{"url":"http://127.0.0.1:3250/","port":3250,"action":"started"}');
    const first = m.viewers.originFor("/proj");
    await settle();
    announce(0);
    await first;
    // Ten crashes, each after ten minutes up: never an nth in a row.
    for (let crash = 0; crash < 10; crash += 1) {
      clock += 10 * 60_000;
      m.children[crash]!.child.exit(1);
      await settle();
      expect(m.children).toHaveLength(crash + 2);
      announce(crash + 1);
      await settle();
    }
    expect(m.delays).toEqual(Array(10).fill(1000));
    // The last forgiven restart is attempt 1, so four more quick crashes in a
    // row are restarted (attempts 2 to 5) and the fifth is given up on.
    const base = m.children.length;
    for (let crash = 0; crash < 4; crash += 1) {
      clock += 1_000;
      m.children.at(-1)!.child.exit(1);
      await settle();
      announce(m.children.length - 1);
      await settle();
    }
    expect(m.children).toHaveLength(base + 4);
    clock += 1_000;
    m.children.at(-1)!.child.exit(1);
    await settle();
    expect(m.children).toHaveLength(base + 4);
  });

  it("a launch asked for after a stop is its own, not the stopped one it would have joined", async () => {
    const m = manager();
    const first = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    m.viewers.stop("/proj");
    const second = m.viewers.originFor("/proj");
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(2);
    m.children[1]!.child.say('{"url":"http://127.0.0.1:3251/","port":3251,"action":"started"}');
    expect(await second).toEqual({ origin: "http://127.0.0.1:3251" });
    expect(await first).toMatchObject({ origin: null, reason: "viewer-failed", message: expect.stringContaining("stopped while launching") });
    expect(m.children[0]!.child.killed).toBe(true);
    expect(m.viewers.list()).toEqual([{ root: "/proj", origin: "http://127.0.0.1:3251", reused: false, pid: 4242 }]);
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

  it("a stop while the runtime resolves does not spawn a second viewer", async () => {
    let release!: () => void;
    const m = manager({ gate: new Promise<void>((resolve) => (release = resolve)) });
    const first = m.viewers.originFor("/proj");
    m.viewers.stop("/proj");
    const second = m.viewers.originFor("/proj");
    release();
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(1);
    m.children[0]!.child.say('{"url":"http://127.0.0.1:3253/","port":3253,"action":"started"}');
    expect(await second).toEqual({ origin: "http://127.0.0.1:3253" });
    expect(await first).toMatchObject({ origin: null, reason: "viewer-failed", message: expect.stringContaining("stopped while launching") });
  });

  it("stopAll stops a root still launching, so the next ask starts its own", async () => {
    const m = manager();
    const first = m.viewers.originFor("/p");
    await new Promise((resolve) => setImmediate(resolve));
    m.viewers.stopAll();
    const second = m.viewers.originFor("/p");
    await new Promise((resolve) => setImmediate(resolve));
    expect(m.children).toHaveLength(2);
    expect(m.children[0]!.child.killed).toBe(true);
    m.children[1]!.child.say('{"url":"http://127.0.0.1:3252/","port":3252,"action":"started"}');
    expect(await second).toEqual({ origin: "http://127.0.0.1:3252" });
    expect(await first).toMatchObject({ origin: null, reason: "viewer-failed" });
  });

  describe("the bound on live viewers", () => {
    const settle = () => new Promise((resolve) => setImmediate(resolve));
    async function bring(m: ReturnType<typeof manager>, root: string, port: number) {
      const pending = m.viewers.originFor(root);
      await settle();
      m.children.at(-1)!.child.say(`{"url":"http://127.0.0.1:${port}/","port":${port},"action":"started"}`);
      await pending;
    }

    it("stops the least recently asked-for viewer when a fourth root comes up", async () => {
      const m = manager();
      await bring(m, "/a", 1);
      await bring(m, "/b", 2);
      await bring(m, "/c", 3);
      await m.viewers.originFor("/a"); // /a is now newer than /b
      await bring(m, "/d", 4);
      expect(m.children.map((entry) => entry.child.killed)).toEqual([false, true, false, false]);
      expect(m.viewers.list().map((entry) => entry.root).sort()).toEqual(["/a", "/c", "/d"]);
    });

    it("never stops a root with a CAD tab open, even the oldest", async () => {
      const m = manager({ inUse: () => ["/a"] });
      await bring(m, "/a", 1);
      await bring(m, "/b", 2);
      await bring(m, "/c", 3);
      await bring(m, "/d", 4);
      expect(m.children.map((entry) => entry.child.killed)).toEqual([false, true, false, false]);
      expect(m.viewers.list().map((entry) => entry.root).sort()).toEqual(["/a", "/c", "/d"]);
    });
  });
});

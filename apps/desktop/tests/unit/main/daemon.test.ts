import { describe, expect, it } from "vitest";

import { DAEMON_ARGS, DaemonWarmer } from "@main/cad/daemon";

/**
 * The daemon warmer only ever spawns `python -m cadgen.daemon` — the
 * registered command a cadgen client would spawn on its own — detached,
 * once per interpreter per app run, and never when the person has turned
 * the daemon off. The spawn is a fake here; what it is given is the test.
 */
function warmer(options: { env?: Record<string, string>; fail?: boolean } = {}) {
  const spawns: Array<{ python: string; args: string[]; cwd: string; env: Record<string, string>; logFile: string; unrefs: number }> = [];
  const logs: string[] = [];
  const daemon = new DaemonWarmer({
    env: (resolved) => ({ ...resolved.env, ...(options.env ?? {}) }),
    logFile: () => "/data/cad-runtime.log",
    spawn: (python, args, spawnOptions) => {
      if (options.fail) {
        throw new Error("ENOENT");
      }
      const record = { python, args, cwd: spawnOptions.cwd, env: spawnOptions.env, logFile: spawnOptions.logFile, unrefs: 0 };
      spawns.push(record);
      return {
        pid: 777,
        unref() {
          record.unrefs += 1;
        },
      };
    },
    log: (line) => logs.push(line),
  });
  return { daemon, spawns, logs };
}

const resolved = { python: "/py", source: "checkout" as const, env: { PYTHONPATH: "/src", CADGEN_NODE: "/electron" } };

describe("DaemonWarmer", () => {
  it("starts the daemon as cadgen's own command, detached, in the cadgen environment", () => {
    const w = warmer();
    expect(w.daemon.warm(resolved, "/proj")).toBe(true);
    expect(w.spawns).toHaveLength(1);
    const [spawn] = w.spawns;
    expect(spawn!.python).toBe("/py");
    expect(spawn!.args).toEqual(DAEMON_ARGS);
    expect(spawn!.args).toEqual(["-m", "cadgen.daemon"]);
    expect(spawn!.cwd).toBe("/proj");
    expect(spawn!.env.PYTHONPATH).toBe("/src");
    expect(spawn!.env.CADGEN_NODE).toBe("/electron");
    expect(spawn!.logFile).toBe("/data/cad-runtime.log");
    // Detached: the app must not wait for it on quit.
    expect(spawn!.unrefs).toBe(1);
    expect(w.logs).toEqual(["warming checkout /py (pid 777)"]);
    expect(w.daemon.list()).toEqual(["/py"]);
  });

  it("warms once per interpreter per app run", () => {
    const w = warmer();
    expect(w.daemon.warm(resolved, "/proj")).toBe(true);
    expect(w.daemon.warm(resolved, "/other")).toBe(false);
    expect(w.daemon.warm({ ...resolved, python: "/py2" }, "/proj")).toBe(true);
    expect(w.spawns.map((spawn) => spawn.python)).toEqual(["/py", "/py2"]);
  });

  it("starts nothing when the person turned the daemon off", () => {
    const w = warmer({ env: { CADGEN_DAEMON: "0" } });
    expect(w.daemon.warm(resolved, "/proj")).toBe(false);
    expect(w.spawns).toHaveLength(0);
    expect(w.daemon.list()).toEqual([]);
  });

  it("a spawn that fails is logged and can be tried again", () => {
    const w = warmer({ fail: true });
    expect(w.daemon.warm(resolved, "/proj")).toBe(false);
    expect(w.logs).toEqual(["could not start the daemon: ENOENT"]);
    expect(w.daemon.list()).toEqual([]);
  });
});

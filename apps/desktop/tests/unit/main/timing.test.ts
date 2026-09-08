import { describe, expect, it } from "vitest";

import { LOAD_PHASES, PhaseTimer, createTimer, loadTimer } from "@main/acp/timing";

/**
 * The line `SessionManager.load` logs is the only measurement of why opening
 * a session took what it took (README, "Opening a session"), and every
 * number in that section came out of it — so the arithmetic is a test rather
 * than a hope: each phase is measured from the one before it, the phases
 * nobody marked are left out, and the total is the whole wait.
 */
describe("PhaseTimer", () => {
  /** A clock the test moves by hand. */
  function clock(start = 1_000) {
    let now = start;
    return { now: () => now, advance: (ms: number) => (now += ms) };
  }

  it("prints each phase as the time since the one before it, and the total", () => {
    const time = clock();
    const timer = loadTimer(time.now);
    time.advance(2);
    timer.mark("spawn");
    time.advance(1_043);
    timer.mark("initialize");
    time.advance(1_398);
    timer.mark("firstUpdate");
    time.advance(2);
    timer.mark("replay");

    expect(timer.deltas()).toEqual([
      { phase: "spawn", ms: 2 },
      { phase: "initialize", ms: 1_043 },
      { phase: "firstUpdate", ms: 1_398 },
      { phase: "replay", ms: 2 },
    ]);
    expect(timer.format()).toBe("spawn=2ms initialize=1043ms firstUpdate=1398ms replay=2ms total=2445ms");
  });

  /**
   * Claude's adapter replays a whole transcript and *then* answers
   * `session/load`, so `firstUpdate` and `replay` land a millisecond apart;
   * an adapter with nothing to replay marks neither. Either way the line has
   * to read, which means a missing phase is absent rather than zero.
   */
  it("leaves out a phase nobody marked", () => {
    const time = clock();
    const timer = loadTimer(time.now);
    time.advance(5);
    timer.mark("spawn");
    time.advance(700);
    timer.mark("initialize");
    time.advance(150);
    timer.mark("replay");

    expect(timer.format()).toBe("spawn=5ms initialize=700ms replay=150ms total=855ms");
    expect(timer.deltas().map((entry) => entry.phase)).not.toContain("firstUpdate");
  });

  /** The first replay update is the one worth knowing; the next thousand are not. */
  it("keeps the first mark of a phase", () => {
    const time = clock();
    const timer = loadTimer(time.now);
    timer.mark("spawn");
    time.advance(40);
    timer.mark("spawn");
    expect(timer.deltas()).toEqual([{ phase: "spawn", ms: 0 }]);
  });

  it("prints in the declared order, whatever order the marks arrived in", () => {
    const time = clock();
    const timer = new PhaseTimer(LOAD_PHASES, time.now);
    time.advance(10);
    timer.mark("replay");
    // Out of order is a bug elsewhere, but the line must still be readable:
    // the order is the declaration's, and a later mark cannot come first.
    timer.mark("spawn");
    expect(timer.deltas().map((entry) => entry.phase)).toEqual(["spawn", "replay"]);
  });

  it("gives create its own phases: there is no transcript to replay", () => {
    const time = clock();
    const timer = createTimer(time.now);
    time.advance(3);
    timer.mark("spawn");
    time.advance(660);
    timer.mark("initialize");
    time.advance(226);
    timer.mark("session/new");
    expect(timer.format()).toBe("spawn=3ms initialize=660ms session/new=226ms total=889ms");
  });
});

import { describe, expect, it } from "vitest";

import { KEEP_ALIVE_LIMIT, LiveConnections } from "@main/acp/live";

/**
 * The adapters that stay alive behind the sessions that are not on screen
 * (README, "Opening a session"). Switching back to one of them is a paint;
 * what it costs is a process per session, so the set is bounded — and the
 * two things it must never close are the session in use and a turn in
 * flight.
 */

class FakeConnection {
  closed = 0;
  alive = true;
  busy = false;

  constructor(readonly name: string) {}

  close(): void {
    this.closed += 1;
    this.alive = false;
  }
}

function pool(limit?: number) {
  const evicted: string[] = [];
  const connections = new LiveConnections<FakeConnection>({
    ...(limit === undefined ? {} : { limit }),
    busy: (connection) => connection.busy,
    onEvict: (sessionId) => evicted.push(sessionId),
  });
  return { connections, evicted };
}

describe("LiveConnections", () => {
  it("keeps the limit and closes the oldest beyond it", () => {
    const { connections, evicted } = pool(2);
    const a = new FakeConnection("a");
    const b = new FakeConnection("b");
    const c = new FakeConnection("c");
    connections.set("a", a);
    connections.set("b", b);
    expect(connections.size).toBe(2);
    connections.set("c", c);
    expect(a.closed).toBe(1);
    expect(connections.keys()).toEqual(["b", "c"]);
    expect(evicted).toEqual(["a"]);
  });

  /** A session touched is a session in use; the queue is by use, not by age. */
  it("touch moves a session to the front, so use decides what survives", () => {
    const { connections } = pool(2);
    const a = new FakeConnection("a");
    connections.set("a", a);
    connections.set("b", new FakeConnection("b"));
    connections.touch("a");
    connections.set("c", new FakeConnection("c"));
    expect(a.closed).toBe(0);
    expect(connections.keys()).toEqual(["a", "c"]);
  });

  it("never closes the connection just used, even at a limit of one", () => {
    const { connections } = pool(1);
    const a = new FakeConnection("a");
    const b = new FakeConnection("b");
    connections.set("a", a);
    connections.set("b", b);
    expect(b.closed).toBe(0);
    expect(connections.keys()).toEqual(["b"]);
  });

  /**
   * An agent halfway through a turn would lose the work and the reason both,
   * so the limit is exceeded rather than enforced — and comes back down when
   * the turn ends.
   */
  it("skips a running turn and closes the next oldest instead", () => {
    const { connections, evicted } = pool(2);
    const busy = new FakeConnection("busy");
    busy.busy = true;
    const idle = new FakeConnection("idle");
    connections.set("busy", busy);
    connections.set("idle", idle);
    connections.set("new", new FakeConnection("new"));
    expect(busy.closed).toBe(0);
    expect(idle.closed).toBe(1);
    expect(evicted).toEqual(["idle"]);
    expect(connections.keys()).toEqual(["busy", "new"]);
  });

  it("exceeds the limit rather than close a busy connection", () => {
    const { connections, evicted } = pool(1);
    const busy = new FakeConnection("busy");
    busy.busy = true;
    connections.set("busy", busy);
    connections.set("new", new FakeConnection("new"));
    expect(busy.closed).toBe(0);
    expect(connections.size).toBe(2);
    expect(evicted).toEqual([]);

    // The turn ends, and the next session brings the count back down to the
    // limit — which at one is the session just used and nothing else.
    busy.busy = false;
    connections.set("newer", new FakeConnection("newer"));
    expect(busy.closed).toBe(1);
    expect(connections.keys()).toEqual(["newer"]);
  });

  /** A crashed adapter holds a slot nobody can use. It goes first, and for free. */
  it("drops dead connections before evicting a live one", () => {
    const { connections, evicted } = pool(2);
    const dead = new FakeConnection("dead");
    dead.alive = false;
    const alive = new FakeConnection("alive");
    connections.set("dead", dead);
    connections.set("alive", alive);
    connections.set("new", new FakeConnection("new"));
    expect(alive.closed).toBe(0);
    // Dead is forgotten, not closed again, and is not reported as an eviction.
    expect(dead.closed).toBe(0);
    expect(evicted).toEqual([]);
    expect(connections.keys()).toEqual(["alive", "new"]);
  });

  it("delete forgets without closing: the caller owns it from there", () => {
    const { connections } = pool();
    const a = new FakeConnection("a");
    connections.set("a", a);
    expect(connections.delete("a")).toBe(a);
    expect(a.closed).toBe(0);
    expect(connections.get("a")).toBeUndefined();
    expect(connections.delete("a")).toBeUndefined();
  });

  it("re-setting a session replaces it in place rather than adding a second slot", () => {
    const { connections } = pool(2);
    connections.set("a", new FakeConnection("a1"));
    connections.set("a", new FakeConnection("a2"));
    expect(connections.size).toBe(1);
    expect(connections.get("a")!.name).toBe("a2");
  });

  it("defaults to the keep-alive limit", () => {
    const { connections } = pool();
    for (let index = 0; index <= KEEP_ALIVE_LIMIT + 2; index += 1) {
      connections.set(`s${index}`, new FakeConnection(`s${index}`));
    }
    expect(connections.size).toBe(KEEP_ALIVE_LIMIT);
  });
});

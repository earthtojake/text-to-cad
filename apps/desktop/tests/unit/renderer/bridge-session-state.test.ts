import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { subscribeToMain } from "@renderer/state/bridge";
import { useSessions } from "@renderer/state/sessions";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

/**
 * A `session.state` main broadcast before it heard the session was archived — or after it was
 * deleted — must not put that session's state back: nothing would forget it again.
 */

type Handler = (payload: unknown) => void;
const bridge = window.textToCad as unknown as Record<string, unknown>;
const saved = bridge.on;
let handlers: Record<string, Handler>;
let detach: () => void;

const row = (id: string, archived = false) => ({ id, projectId: "p1", agentId: "codex", title: id, cwd: "/p1", status: "idle", archived }) as unknown as Session;
const broadcast = (sessionId: string) =>
  handlers["session.state"]!({ sessionId, state: { ...initialSessionState(sessionId, "codex"), status: "running" } });

beforeEach(() => {
  handlers = {};
  bridge.on = vi.fn((channel: string, handler: Handler) => { handlers[channel] = handler; return () => {}; });
  useSessions.setState({ sessions: [row("live"), row("archived", true)], ready: true, activeId: null });
  useAcp.setState({ sessions: {}, loading: {}, reconnecting: {}, loadErrors: {}, terminalOutput: {} });
  detach = subscribeToMain();
});

afterEach(() => {
  detach();
  bridge.on = saved;
});

it("takes a session's state from main, but not an archived or deleted session's", () => {
  broadcast("live");
  broadcast("archived");
  broadcast("deleted");
  expect(Object.keys(useAcp.getState().sessions)).toEqual(["live"]);
});

/**
 * An archived session open on screen is a session main reconnects on a prompt; the `session.state`
 * that ends that load is the one that replaces the replayed transcript, so it is taken.
 */
it("takes an archived session's state while the renderer still holds that session", () => {
  useAcp.setState({ sessions: { archived: initialSessionState("archived", "codex") } });
  broadcast("archived");
  expect(useAcp.getState().sessions.archived?.status).toBe("running");
});

/**
 * The state that ends a load drains the prompts queued behind the disconnect — but only when the
 * store took it: one it dropped (a load a Disconnect has since overtaken) sent nothing to drain into.
 */
it("drains the composer for an idle state the store took, and not for one it dropped", () => {
  const drain = vi.fn(async () => {});
  const drained = useComposer.getState().drain;
  const received = useAcp.getState().receiveState;
  useComposer.setState({ drain });
  try {
    const idle = (sessionId: string) =>
      handlers["session.state"]!({ sessionId, state: { ...initialSessionState(sessionId, "codex"), status: "idle" } });
    idle("live");
    expect(drain).toHaveBeenCalledWith("live");

    drain.mockClear();
    useAcp.setState({ receiveState: () => {} });
    idle("live");
    expect(drain).not.toHaveBeenCalled();
  } finally {
    useComposer.setState({ drain: drained });
    useAcp.setState({ receiveState: received });
  }
});

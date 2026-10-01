import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { subscribeToMain } from "@renderer/state/bridge";
import { useSessions } from "@renderer/state/sessions";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

/**
 * A create that failed after `session/new` leaves the row idle with the failure as a note in
 * `session.status.error` (`settleAfterFailedCreate`). Main sends it on a channel of its own, and
 * the note has to reach the person: without it the session looks like a healthy idle one.
 */
vi.mock("@renderer/features/session/Composer", () => ({
  Composer: ({ disabled }: { disabled: boolean }) => <textarea aria-label="Prompt" disabled={disabled} />,
}));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/Transcript", () => ({ Transcript: () => <div data-transcript /> }));
vi.mock("@renderer/features/session/ContextMeter", () => ({ ContextMeter: () => null }));

const NOTE = "The session started, but setting it up failed: SQLITE_BUSY";
const SESSION = { id: "s1", projectId: "p1", agentId: "claude", cwd: "/p", title: "t", status: "idle" } as unknown as Session;

type Handler = (payload: unknown) => void;
const bridge = window.textToCad as unknown as Record<string, unknown>;
const saved = { on: bridge.on, sessions: bridge.sessions };
let handlers: Record<string, Handler>;
let detach: () => void;
const load = vi.fn(async () => ({ ...initialSessionState("s1", "claude"), status: "idle" as const }));
const retrySetup = vi.fn(async (_input: { id: string }): Promise<{ error: string | null }> => ({ error: null }));
const close = vi.fn(async () => undefined);

beforeEach(() => {
  handlers = {};
  bridge.on = vi.fn((channel: string, handler: Handler) => { handlers[channel] = handler; return () => {}; });
  bridge.sessions = { ...(saved.sessions as object), load, retrySetup, close };
  load.mockClear();
  retrySetup.mockClear();
  close.mockClear();
  useSessions.setState({ sessions: [SESSION], ready: true, activeId: null });
  useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "claude"), status: "idle" } }, loading: {}, reconnecting: {}, loadErrors: {}, setupNotes: {}, terminalOutput: {} });
  detach = subscribeToMain();
});

afterEach(() => {
  detach();
  bridge.on = saved.on;
  bridge.sessions = saved.sessions;
});

const emitNote = (error: string | null, status = "idle") =>
  act(() => {
    handlers["session.state"]!({ sessionId: "s1", state: { ...initialSessionState("s1", "claude"), status: "idle" } });
    handlers["session.status"]!({ sessionId: "s1", status, error });
  });

describe("the note a failed setup leaves", () => {
  it("is shown above a composer that stays sendable, and survives an ordinary status change", () => {
    render(<SessionView session={SESSION} />);
    expect(screen.queryByRole("alert")).toBeNull();
    emitNote(NOTE);
    expect(screen.getByRole("alert")).toHaveTextContent(NOTE);
    expect(screen.getByLabelText("Prompt")).toBeEnabled();
    act(() => handlers["session.status"]!({ sessionId: "s1", status: "running", error: null }));
    expect(screen.getByRole("alert")).toHaveTextContent(NOTE);
  });

  it("is not taken from an error or closed status, whose message the load failure already shows", () => {
    render(<SessionView session={SESSION} />);
    expect(handlers["session.status"], "the bridge listens for statuses").toBeTypeOf("function");
    emitNote("spawn failed", "error");
    emitNote("gone", "closed");
    expect(useAcp.getState().setupNotes).toEqual({});
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Retry setup runs the setup again through its own call, never a load, and goes when it went through", async () => {
    const user = userEvent.setup();
    render(<SessionView session={SESSION} />);
    emitNote(NOTE);
    load.mockClear();
    await user.click(screen.getByRole("button", { name: "Retry setup" }));
    expect(retrySetup).toHaveBeenCalledWith({ id: "s1" });
    expect(load).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(useAcp.getState().reconnecting).toEqual({});
  });

  it("keeps the alert with the new note when the retry fails too", async () => {
    const user = userEvent.setup();
    retrySetup.mockResolvedValueOnce({ error: "Setting it up again failed: SQLITE_BUSY" });
    render(<SessionView session={SESSION} />);
    emitNote(NOTE);
    await user.click(screen.getByRole("button", { name: "Retry setup" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Setting it up again failed"));
  });

  it("goes when the session is disconnected by hand, leaving one Reconnect", async () => {
    render(<SessionView session={SESSION} />);
    emitNote(NOTE);
    expect(screen.getByRole("alert")).toHaveTextContent(NOTE);
    await act(() => useAcp.getState().close("s1"));
    expect(close).toHaveBeenCalledWith({ id: "s1" });
    expect(useAcp.getState().setupNotes).toEqual({});
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getAllByRole("button", { name: /Reconnect|Retry setup/ })).toHaveLength(1);
  });
});

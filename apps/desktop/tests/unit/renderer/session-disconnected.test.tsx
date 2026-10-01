import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { useAgents } from "@renderer/state/agents";
import { useUi } from "@renderer/state/ui";
import type { AgentStatus } from "@shared/agents";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

// The pieces around the one state under test are their own suites.
vi.mock("@renderer/features/session/Composer", () => ({
  Composer: ({ disabled }: { disabled: boolean }) => <textarea aria-label="Prompt" data-composer-input disabled={disabled} />,
}));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
// The error part's Reconnect and Retry live in the transcript; the mock draws Reconnect for a session
// in error and Retry on the last turn, which a resubmit replaces (so the button goes, as it does there).
vi.mock("@renderer/features/session/Transcript", () => ({
  Transcript: ({ state, onReconnect, onRetry }: { state: { status: string; turns: unknown[] }; onReconnect: () => void; onRetry: () => void }) => (
    <div data-transcript>
      {state.status === "error" ? <button onClick={onReconnect} type="button">Reconnect from the transcript</button> : null}
      {state.turns.length === 2 ? <button onClick={onRetry} type="button">Retry from the transcript</button> : null}
    </div>
  ),
}));
vi.mock("@renderer/features/session/ContextMeter", () => ({ ContextMeter: () => null }));

const SESSION = {
  id: "s1",
  projectId: "p1",
  agentId: "claude",
  cwd: "/bracket",
  gitMode: "checkout",
  title: "New session",
  titleSource: "prompt",
  createdAt: 0,
  updatedAt: 0,
  status: "closed",
} as unknown as Session;

const load = vi.fn(async () => undefined);
const ensureLoaded = vi.fn(async () => undefined);

beforeEach(() => {
  load.mockClear();
  ensureLoaded.mockClear();
  useAcp.setState({ sessions: {}, loading: {}, reconnecting: {}, loadErrors: {}, load, ensureLoaded } as never);
});

describe("a disconnected agent", () => {
  it("keeps focus off the page after the transcript's own Reconnect unmounts", async () => {
    const user = userEvent.setup();
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "claude"), status: "error", error: "boom" } } });
    render(<SessionView session={SESSION} />);
    await user.click(screen.getByRole("button", { name: "Reconnect from the transcript" }));
    act(() => useAcp.setState({ loading: { s1: true }, sessions: { s1: { ...initialSessionState("s1", "claude"), status: "connecting" } } }));
    expect(screen.queryByRole("button", { name: "Reconnect from the transcript" })).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
  });

  it("hands focus to the composer when the transcript's own Retry resubmits and goes", async () => {
    const user = userEvent.setup();
    const submit = vi.fn(async () => undefined);
    useComposer.setState({ submit } as never);
    const failed = {
      ...initialSessionState("s1", "claude"),
      status: "idle" as const,
      turns: [
        { id: "t1", role: "user", startedAt: 0, parts: [{ type: "text", text: "hello" }] },
        { id: "t2", role: "agent", startedAt: 0, parts: [{ type: "error", message: "boom" }] },
      ],
    };
    useAcp.setState({ sessions: { s1: failed as never } });
    render(<SessionView session={SESSION} />);
    await user.click(screen.getByRole("button", { name: "Retry from the transcript" }));
    expect(submit).toHaveBeenCalledWith("s1", "hello", [{ type: "text", text: "hello" }]);
    // The resubmit appends a turn: Retry goes with the last turn, and focus is not on the page.
    act(() => useAcp.setState({ sessions: { s1: { ...failed, status: "running", turns: [...failed.turns, { id: "t3", role: "user", startedAt: 0, parts: [] }] } as never } }));
    expect(screen.queryByRole("button", { name: "Retry from the transcript" })).toBeNull();
    expect(screen.getByLabelText("Prompt")).toHaveFocus();
  });

  it("says so above the disabled composer and reconnects from there", async () => {
    const user = userEvent.setup();
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "claude"), status: "closed" } } });
    render(<SessionView session={SESSION} />);

    expect(screen.getByRole("status")).toHaveTextContent("Agent disconnected");
    expect(screen.getByLabelText("Prompt")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    expect(load).toHaveBeenCalledWith("s1");
  });

  it("keeps focus off the page after Reconnect, and hands it to the composer once the agent is back", async () => {
    const user = userEvent.setup();
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "claude"), status: "closed" } } });
    render(<SessionView session={SESSION} />);
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    // The bar goes with the reconnect: its button is gone, and focus is not on the page.
    act(() => useAcp.setState({ loading: { s1: true }, sessions: { s1: { ...initialSessionState("s1", "claude"), status: "connecting" } } }));
    expect(screen.queryByRole("button", { name: "Reconnect" })).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
    act(() => useAcp.setState({ loading: {}, sessions: { s1: { ...initialSessionState("s1", "claude"), status: "idle" } } }));
    await waitFor(() => expect(screen.getByLabelText("Prompt")).toHaveFocus());
  });

  it("stays disconnected, not connecting, once a closed transcript is let go of", () => {
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "claude"), status: "closed" } } });
    render(<SessionView session={SESSION} />);
    act(() => useAcp.getState().forget("s1"));

    expect(screen.getByRole("status")).toHaveTextContent("Agent disconnected");
    expect(screen.queryByText(/Connecting to/)).toBeNull();
  });

  it("is not claimed for a closed row opened for the first time, which is still loading", () => {
    render(<SessionView session={SESSION} />);

    expect(screen.queryByText("Agent disconnected")).toBeNull();
    expect(screen.getByText(/Connecting to/)).toBeInTheDocument();
  });
});

describe("an agent whose CLI is not installed", () => {
  const missing = {
    id: "claude",
    name: "Claude Code",
    icon: null,
    installed: false,
    launchWithoutBinary: false,
    auth: "unknown",
    authMethods: [],
  } as unknown as AgentStatus;

  it("offers the install and Settings › Agents instead of a Reconnect that fails again", async () => {
    const user = userEvent.setup();
    const install = vi.fn(async () => "job1");
    const openSettings = vi.fn();
    useAgents.setState({ agents: [missing], jobs: {}, ready: true, install } as never);
    useUi.setState({ openSettings } as never);
    useAcp.setState({ loadErrors: { s1: "Claude Code is not installed" } });
    render(<SessionView session={SESSION} />);

    expect(screen.queryByRole("button", { name: "Reconnect" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Install" }));
    expect(install).toHaveBeenCalledWith("claude");
    await user.click(screen.getByRole("button", { name: "Settings › Agents" }));
    expect(openSettings).toHaveBeenCalledWith("agents");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(load).toHaveBeenCalledWith("s1");
  });

  it("does the same above a painted transcript", () => {
    useAgents.setState({ agents: [missing], jobs: {}, ready: true });
    useAcp.setState({
      sessions: { s1: { ...initialSessionState("s1", "claude"), status: "closed" } },
      loadErrors: { s1: "Claude Code is not installed" },
    });
    render(<SessionView session={SESSION} />);
    expect(screen.getByText("Claude Code is not installed", { selector: "p.font-medium" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reconnect" })).toBeNull();
  });
});

describe("a load that failed with nothing painted", () => {
  // Drawn where the transcript would be, so nothing had moved focus or said anything: a screen reader
  // heard no failure, and Reconnect was the only way out.
  it("is announced as an alert", () => {
    useAcp.setState({ loadErrors: { s1: "spawn failed" } });
    render(<SessionView session={SESSION} />);
    expect(screen.getByRole("alert")).toHaveTextContent("spawn failed");
  });

  it("keeps focus off the page once its Reconnect has unmounted, and says it is connecting", async () => {
    const user = userEvent.setup();
    useAcp.setState({ loadErrors: { s1: "spawn failed" } });
    render(<SessionView session={SESSION} />);
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    // The load starts: the failure panel and its button go, the connecting screen takes their place.
    act(() => useAcp.setState({ loading: { s1: true }, loadErrors: {} }));
    expect(screen.queryByRole("button", { name: "Reconnect" })).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
    expect(screen.getByRole("status")).toHaveTextContent("Connecting to");
  });
});

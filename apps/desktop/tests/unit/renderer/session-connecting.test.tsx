import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

// The composer is its own suite; this one reads what SessionView hands it.
vi.mock("@renderer/features/session/Composer", () => ({
  Composer: ({ disabled, status }: { disabled: boolean; status: string }) => (
    <textarea aria-label="Prompt" data-composer-input data-status={status} disabled={disabled} />
  ),
}));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/Transcript", () => ({ Transcript: () => <div data-transcript /> }));
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
  status: "idle",
} as unknown as Session;

beforeEach(() => {
  useAcp.setState({
    sessions: { s1: { ...initialSessionState("s1", "claude"), status: "idle" } },
    loading: {},
    reconnecting: {},
    loadErrors: {},
    ensureLoaded: vi.fn(async () => undefined),
  } as never);
  useComposer.setState({ sending: {} });
});

describe("a session still being created", () => {
  it("holds the composer while its row says connecting, though the agent's state reads idle", () => {
    render(<SessionView session={{ ...SESSION, status: "connecting" }} />);
    expect(screen.getByLabelText("Prompt")).toBeDisabled();
  });

  it("does not hold the composer of a reconnecting session whose row says connecting", () => {
    useAcp.setState({ reconnecting: { s1: true } });
    render(<SessionView session={{ ...SESSION, status: "connecting" }} />);
    expect(screen.getByLabelText("Prompt")).toBeEnabled();
  });
});

describe("a prompt sent with no turn started", () => {
  it("shows as submitted while the store holds it in `sending`", () => {
    useComposer.setState({ sending: { s1: 1 } });
    render(<SessionView session={SESSION} />);
    expect(screen.getByLabelText("Prompt")).toHaveAttribute("data-status", "submitted");
  });

  it("is ready when nothing is in flight", () => {
    render(<SessionView session={SESSION} />);
    expect(screen.getByLabelText("Prompt")).toHaveAttribute("data-status", "ready");
  });
});

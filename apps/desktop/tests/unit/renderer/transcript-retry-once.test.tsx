import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { PartsList } from "@renderer/features/session/parts/PartsList";
import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

vi.mock("@renderer/features/session/Composer", () => ({ Composer: () => <textarea aria-label="Prompt" data-composer-input /> }));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/ContextMeter", () => ({ ContextMeter: () => null }));
// Retry stays on screen, as it does while the resend is out and the turn has not begun.
vi.mock("@renderer/features/session/Transcript", () => ({
  Transcript: ({ onRetry }: { onRetry: () => void }) => <button onClick={onRetry} type="button">Retry from the transcript</button>,
}));

const SESSION = { id: "s1", projectId: "p1", agentId: "claude", cwd: "/b", gitMode: "checkout", title: "t", titleSource: "prompt", createdAt: 0, updatedAt: 0, status: "idle" } as unknown as Session;

beforeEach(() => {
  useAcp.setState({ sessions: {}, loading: {}, reconnecting: {}, loadErrors: {}, load: vi.fn(async () => undefined), ensureLoaded: vi.fn(async () => undefined) } as never);
});

it("a second Retry click while the resend is out sends nothing and queues nothing", async () => {
  const user = userEvent.setup();
  let settle: () => void = () => {};
  const submit = vi.fn(() => new Promise<void>((resolve) => { settle = resolve; }));
  useComposer.setState({ submit, queues: {} } as never);
  useAcp.setState({
    sessions: {
      s1: {
        ...initialSessionState("s1", "claude"),
        status: "idle" as const,
        turns: [
          { id: "t1", role: "user", startedAt: 0, parts: [{ type: "text", text: "hello" }] },
          { id: "t2", role: "agent", startedAt: 0, parts: [{ type: "error", message: "boom" }] },
        ],
      } as never,
    },
  });
  render(<SessionView session={SESSION} />);
  const retry = screen.getByRole("button", { name: "Retry from the transcript" });
  await user.click(retry);
  await user.click(retry);
  expect(submit).toHaveBeenCalledTimes(1);
  expect(useComposer.getState().queues.s1 ?? []).toEqual([]);
  await act(async () => settle());
  await user.click(retry);
  expect(submit).toHaveBeenCalledTimes(2);
});

it("the error row's Retry is disabled from the first click until the resend settles", async () => {
  const user = userEvent.setup();
  let settle: () => void = () => {};
  const onRetry = vi.fn(() => new Promise<void>((resolve) => { settle = resolve; }));
  render(<PartsList onRetry={onRetry} open={false} parts={[{ type: "error", message: "boom" } as never]} prefix="t" sessionId="s1" />);
  await user.click(screen.getByRole("button", { name: "Retry" }));
  const pending = screen.getByRole("button", { name: "Retrying…" });
  expect((pending as HTMLButtonElement).disabled).toBe(true);
  await user.click(pending);
  expect(onRetry).toHaveBeenCalledTimes(1);
  await act(async () => settle());
  expect((screen.getByRole("button", { name: "Retry" }) as HTMLButtonElement).disabled).toBe(false);
});

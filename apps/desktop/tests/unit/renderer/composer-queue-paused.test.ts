import { act, fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { Composer } from "@renderer/features/session/Composer";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import type { PromptBlock } from "@shared/acp/types";
import { initialSessionState } from "@shared/acp/types";
import type { Project } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

/** A queue held back by a failed turn says so, and Resume sends what is next. */
const SESSION = "s1";
const project: Project = { id: "p", name: "p", path: "/p", createdAt: 0 };
const block = (text: string): PromptBlock[] => [{ type: "text", text }];

beforeEach(() => {
  useProjects.setState({ projects: [project], activeId: project.id });
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {}, paused: {} });
});

it("a paused queue shows why, and Resume clears the pause and sends the head", async () => {
  const prompt = vi.fn(() => new Promise<string>(() => {}));
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle" } }, prompt });
  useComposer.getState().enqueue(SESSION, "A", block("A"));
  useComposer.getState().enqueue(SESSION, "B", block("B"));
  render(createElement(Composer, { sessionId: SESSION, newDraftKey: "__new__:p", chips: null, commands: [], status: "ready", onSubmit: vi.fn() }));
  expect(screen.queryByText("Paused after an error")).toBeNull();
  expect(screen.getByRole("status", { hidden: true }), "the live region is there before the pause, empty").toBeTruthy();

  // What main does on a failed turn: the turn errors and the session reads "error" until the next.
  act(() => {
    useComposer.getState().turnEvent(SESSION, "prompt/error");
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "error" } } });
  });
  expect(screen.getByRole("status").textContent).toBe("Paused after an error");
  expect(screen.getByRole("status").contains(screen.getByRole("button", { name: "Resume" })), "the button sits outside the live region").toBe(false);

  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Resume" })); });
  expect(screen.queryByText("Paused after an error")).toBeNull();
  expect(prompt).toHaveBeenCalledWith(SESSION, block("A"));
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["B"]);
});

it("a turn the person stopped holds the queue: it is not drained, says so, and Resume sends the head", async () => {
  const prompt = vi.fn(() => new Promise<string>(() => {}));
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "running" } }, prompt });
  useComposer.getState().enqueue(SESSION, "A", block("A"));
  useComposer.getState().enqueue(SESSION, "B", block("B"));
  render(createElement(Composer, { sessionId: SESSION, newDraftKey: "__new__:p", chips: null, commands: [], status: "ready", onSubmit: vi.fn() }));

  // What the bridge does when Stop ends the running turn: `prompt/end` with `cancelled`, then idle.
  await act(async () => {
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle", turns: [{ id: "t", stopReason: "cancelled" } as never] } } });
    useComposer.getState().turnEvent(SESSION, "prompt/end", "cancelled");
  });
  expect(prompt, "Stop must not start the next queued prompt").not.toHaveBeenCalled();
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["A", "B"]);
  expect(screen.getByRole("status").textContent).toBe("Paused after you stopped");

  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Resume" })); });
  expect(prompt).toHaveBeenCalledWith(SESSION, block("A"));
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["B"]);
});

it("a Resume that main refuses before any turn reads 'Paused after an error', not 'after you stopped'", async () => {
  // The agent is gone: main refuses the head before a turn begins, so the last turn is still the
  // one the person stopped.
  const prompt = vi.fn(() => Promise.reject(new Error("the agent is not installed")));
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "running" } }, prompt, loadErrors: {} });
  useComposer.getState().enqueue(SESSION, "A", block("A"));
  useComposer.getState().enqueue(SESSION, "B", block("B"));
  render(createElement(Composer, { sessionId: SESSION, newDraftKey: "__new__:p", chips: null, commands: [], status: "ready", onSubmit: vi.fn() }));
  await act(async () => {
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle", turns: [{ id: "t", stopReason: "cancelled" } as never] } } });
    useComposer.getState().turnEvent(SESSION, "prompt/end", "cancelled");
  });
  expect(screen.getByRole("status").textContent).toBe("Paused after you stopped");

  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Resume" })); });
  expect(prompt).toHaveBeenCalledTimes(1);
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["A", "B"]);
  expect(screen.getByRole("status").textContent).toBe("Paused after an error");
});

it("Stop with nothing queued does not pause: the next prompt is not held back behind a pause nobody can see", async () => {
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle" } } });
  await act(async () => { useComposer.getState().turnEvent(SESSION, "prompt/end", "cancelled"); });
  expect(useComposer.getState().paused).toEqual({});
});

it("a turn that ends normally still drains the queue", async () => {
  const prompt = vi.fn(() => new Promise<string>(() => {}));
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle" } }, prompt });
  useComposer.getState().enqueue(SESSION, "A", block("A"));
  await act(async () => { useComposer.getState().turnEvent(SESSION, "prompt/end", "end_turn"); });
  expect(prompt).toHaveBeenCalledWith(SESSION, block("A"));
});

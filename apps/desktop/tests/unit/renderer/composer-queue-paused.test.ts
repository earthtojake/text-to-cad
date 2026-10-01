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

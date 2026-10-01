import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Composer } from "@renderer/features/session/Composer";
import { SubagentRow } from "@renderer/features/session/parts/SubagentRow";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";

/**
 * Two hints that must show the full name when the row or chip clips it — and only then (the kit:
 * no hint that repeats a label, full names only when clipped).
 */

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

const width = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollWidth");
/** jsdom lays nothing out; `clipped` makes every `.truncate` wider than its box. */
function layout(clipped: boolean) {
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return clipped && this.classList.contains("truncate") ? 500 : 0;
    },
  });
}

/** Hover, then let the hint's 400ms delay pass on the fake clock. */
async function hover(element: Element) {
  await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).hover(element);
  act(() => vi.advanceTimersByTime(500));
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {} });
});
afterEach(() => {
  vi.useRealTimers();
  if (width) Object.defineProperty(HTMLElement.prototype, "scrollWidth", width);
});

it("a subagent row with nothing to open still shows its clipped task on hover", async () => {
  layout(true);
  render(<SubagentRow part={{ type: "subagent", sessionId: "c1", name: "Docs checker", task: "confirm every link in the README", state: "completed", parts: [] }} sessionId="s1" />);
  await hover(screen.getByText("confirm every link in the README", { exact: false }));
  expect(await screen.findByRole("tooltip")).toHaveTextContent("confirm every link in the README");
});

async function chip(scoped: boolean) {
  useProjects.setState({ projects: scoped ? [{ id: "p", name: "p", path: "/p", createdAt: 0 }] : [], activeId: scoped ? "p" : null });
  useComposer.getState().setDraft("d", "look at models/x.step#o1 ");
  const view = render(<Composer chips={null} commands={[]} newDraftKey="d" onSubmit={vi.fn()} sessionId={null} status="ready" />);
  await waitFor(() => expect(view.container.querySelector("[data-reference-chip]")).not.toBeNull());
  return view.container.querySelector<HTMLElement>("[data-reference-chip]")!;
}

it("a reference chip shows its whole name when clipped, even with no project to open it in", async () => {
  layout(true);
  const node = await chip(false);
  await hover(node);
  expect(await screen.findByRole("tooltip")).toHaveTextContent("models/x.step#o1");
});

it("a reference chip that is not clipped has no hint: its label already says it", async () => {
  layout(false);
  const node = await chip(true);
  await hover(node.querySelector("button")!);
  expect(screen.queryByRole("tooltip")).toBeNull();
});

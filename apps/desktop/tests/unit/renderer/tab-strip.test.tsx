import { act, createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { EXPLORER_TABPANEL_ID, TabStrip } from "@renderer/features/explorer/TabStrip";
import { useExplorer } from "@renderer/state/explorer";
import type { ExplorerTab } from "@shared/types";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), dismiss: vi.fn() }) }));

const SESSION = "tab-strip-session";
const tab = (id: string, path: string, order: number): ExplorerTab =>
  ({ id, kind: "file", sessionId: SESSION, projectId: SESSION, order, root: null, panel: null, path }) as ExplorerTab;

beforeEach(() => {
  useExplorer.setState({
    sessionId: SESSION, projectId: SESSION, root: null, ready: true, collapsed: false,
    tabs: [tab("a", "a.md", 0), tab("b", "b.md", 1), tab("c", "c.md", 2)], activeId: "b",
  });
});

// Hidden from the accessibility tree (Delete is the keyboard's close), so found by its label.
const closeButton = (title: string) => document.querySelector<HTMLElement>(`button[aria-label="Close ${title}"]`)!;

const strip = () => render(<TooltipProvider><TabStrip /></TooltipProvider>);

it("is one Tab stop: the selected tab, with its close button out of the Tab order", () => {
  strip();
  const tabs = screen.getAllByRole("tab");
  expect(tabs.map((element) => element.tabIndex)).toEqual([-1, 0, -1]);
  expect(tabs[1]).toHaveAttribute("aria-selected", "true");
  expect(tabs[1]).toHaveAttribute("aria-controls", EXPLORER_TABPANEL_ID);
  expect(tabs[0]).not.toHaveAttribute("aria-controls");
  expect(closeButton("b.md")).toHaveAttribute("tabindex", "-1");
});

it("states the selection on the tab itself, and keeps its close button outside the tab (no nested interactive)", () => {
  strip();
  expect(document.querySelectorAll("[role=tab] [aria-selected]")).toHaveLength(0);
  expect(document.querySelectorAll("[role=tab] button")).toHaveLength(0);
  // The pointer's close is a sibling hidden from the accessibility tree: Delete is the keyboard's.
  const close = closeButton("b.md");
  expect(close.closest("[role=tab]")).toBeNull();
  expect(close).toHaveAttribute("aria-hidden", "true");
  expect(screen.getByRole("tab", { name: /b\.md/ })).toHaveAttribute("aria-keyshortcuts", "Delete");
});

it("moves focus with the arrows, Home and End, and selects only on Enter", async () => {
  const user = userEvent.setup();
  strip();
  const [a, b, c] = screen.getAllByRole("tab");
  b!.focus();

  await user.keyboard("{ArrowRight}");
  expect(c).toHaveFocus();
  expect(c).toHaveAttribute("tabindex", "0");
  expect(useExplorer.getState().activeId).toBe("b");
  await user.keyboard("{ArrowRight}");
  expect(a).toHaveFocus();
  await user.keyboard("{ArrowLeft}");
  expect(c).toHaveFocus();
  await user.keyboard("{Home}");
  expect(a).toHaveFocus();
  await user.keyboard("{End}");
  expect(c).toHaveFocus();

  await user.keyboard("{Enter}");
  expect(useExplorer.getState().activeId).toBe("c");
});

it("closes the focused tab on Delete and hands focus to its neighbour", async () => {
  const user = userEvent.setup();
  strip();
  screen.getAllByRole("tab")[0]!.focus();

  await user.keyboard("{Delete}");
  expect(useExplorer.getState().tabs.map((candidate) => candidate.id)).toEqual(["b", "c"]);
  await waitFor(() => expect(screen.getByRole("tab", { name: /b\.md/ })).toHaveFocus());
});

it("closing the last tab on Delete hands focus to New tab, not to the page", async () => {
  useExplorer.setState({ tabs: [tab("a", "a.md", 0)], activeId: "a" });
  const user = userEvent.setup();
  strip();
  screen.getByRole("tab")!.focus();

  await user.keyboard("{Backspace}");
  expect(useExplorer.getState().tabs).toEqual([]);
  await waitFor(() => expect(screen.getByRole("button", { name: "New tab" })).toHaveFocus());
});

it("closing a tab with its close button hands focus to the tab selected next, not to the page", async () => {
  const user = userEvent.setup();
  strip();
  await user.click(closeButton("b.md"));
  expect(useExplorer.getState().tabs.map((candidate) => candidate.id)).toEqual(["a", "c"]);
  const selected = useExplorer.getState().activeId!;
  await waitFor(() => expect(document.querySelector(`[data-tab="${selected}"]`)).toHaveFocus());
});

it("Cmd+W from inside the tab's body hands focus to the tab selected next, not to the page", async () => {
  // The body the strip controls, standing in for Monaco or a terminal: it goes with its tab.
  function Body() {
    const activeId = useExplorer((state) => state.activeId);
    return activeId ? <input aria-label={`Body of ${activeId}`} key={activeId} /> : null;
  }
  render(<TooltipProvider><TabStrip /><div id={EXPLORER_TABPANEL_ID}><Body /></div></TooltipProvider>);
  screen.getByRole("textbox", { name: "Body of b" }).focus();
  act(() => useExplorer.getState().closeActive());
  const selected = useExplorer.getState().activeId!;
  expect(selected).not.toBe("b");
  await waitFor(() => expect(document.querySelector(`[data-tab="${selected}"]`)).toHaveFocus());
});

it("Cmd+W marks the tab it hands focus to, so the strip draws its ring; a click's close does not", async () => {
  const user = userEvent.setup();
  function Body() {
    const activeId = useExplorer((state) => state.activeId);
    return activeId ? <input aria-label={`Body of ${activeId}`} key={activeId} /> : null;
  }
  render(<TooltipProvider><TabStrip /><div id={EXPLORER_TABPANEL_ID}><Body /></div></TooltipProvider>);
  // Reached with the mouse, as Monaco or a terminal is: Chromium draws no ring on the tab then.
  await user.click(screen.getByRole("textbox", { name: "Body of b" }));
  await user.keyboard("{Meta>}w{/Meta}");
  act(() => useExplorer.getState().closeActive());
  const selected = useExplorer.getState().activeId!;
  const tab = document.querySelector(`[data-tab="${selected}"]`)!;
  await waitFor(() => expect(tab).toHaveFocus());
  expect(tab).toHaveAttribute("data-focus-handed");
  // Gone with the focus: a later focus there by pointer draws no ring of this kind.
  act(() => (tab as HTMLElement).blur());
  expect(tab).not.toHaveAttribute("data-focus-handed");

  await user.click(document.querySelector<HTMLElement>('button[aria-label^="Close "]')!);
  await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  expect(document.querySelector("[data-focus-handed]")).toBeNull();
});

it("a tab that goes while the person is elsewhere — transcript text clicked, then an agent's close_tab or a session switch — takes no focus", async () => {
  const user = userEvent.setup();
  render(<TooltipProvider><TabStrip /><p>The agent's words</p></TooltipProvider>);
  // The person was in the strip, then clicked the transcript: focus is the page's.
  screen.getAllByRole("tab")[1]!.focus();
  await user.click(screen.getByText("The agent's words"));
  expect(document.activeElement).toBe(document.body);

  act(() => useExplorer.getState().close("a"));
  expect(useExplorer.getState().tabs.map((candidate) => candidate.id)).toEqual(["b", "c"]);
  await act(async () => {});
  expect(document.activeElement).toBe(document.body);

  act(() => useExplorer.setState({ tabs: [tab("d", "d.md", 0)], activeId: "d" }));
  await act(async () => {});
  expect(document.activeElement).toBe(document.body);
});

it("draws the Terminal shortcut's backtick as a keycap and names it, not as a hairline beside ⌃", async () => {
  strip();
  await userEvent.setup().click(screen.getByRole("button", { name: "New tab" }));
  const terminal = await screen.findByRole("menuitem", { name: /Terminal/ });
  const tick = [...terminal.querySelectorAll("kbd")].find((key) => key.textContent === "`");
  expect(tick, "the backtick is its own keycap").toBeDefined();
  expect(terminal).toHaveTextContent(/backtick/);
  // The others are glyphs and letters, left as they are.
  expect((await screen.findByRole("menuitem", { name: /Review/ })).querySelector("kbd")).toBeNull();
});

// The chip is the drag handle and the drop target; the tab in it is what names it.
const chip = (id: string) => document.querySelector(`[data-tab="${id}"]`)!.closest<HTMLElement>("[draggable]")!;
const order = () => useExplorer.getState().tabs.map((candidate) => candidate.id);
const dataTransfer = () => ({ effectAllowed: "", dropEffect: "none" });
// jsdom has no layout: every chip is 100px wide, so a drag over its left half is x=10 and its right x=90.
const BOX = { left: 0, right: 100, top: 0, bottom: 28, width: 100, height: 28, x: 0, y: 0, toJSON: () => ({}) };
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(BOX as DOMRect);
});
// jsdom has no DragEvent, so the init's clientX is dropped: it is set on the event itself.
const over = (id: string, half: "left" | "right") => {
  const event = createEvent.dragOver(chip(id), { dataTransfer: dataTransfer() });
  Object.defineProperty(event, "clientX", { value: half === "left" ? 10 : 90 });
  fireEvent(chip(id), event);
};

it("leaves the order alone when a drag ends without a drop (Escape, released outside)", () => {
  strip();
  fireEvent.dragStart(chip("a"), { dataTransfer: dataTransfer() });
  over("c", "left");
  fireEvent.dragEnd(chip("a"), { dataTransfer: dataTransfer() });
  expect(order()).toEqual(["a", "b", "c"]);
});

it("drops a tab dragged forward where the line was drawn, before the tab it was over", () => {
  strip();
  fireEvent.dragStart(chip("a"), { dataTransfer: dataTransfer() });
  over("c", "left");
  expect(chip("c").className).toContain("before:w-0.5");
  fireEvent.drop(chip("c"), { dataTransfer: dataTransfer() });
  fireEvent.dragEnd(chip("a"), { dataTransfer: dataTransfer() });
  expect(order()).toEqual(["b", "a", "c"]);
});

it("drops a tab dragged back before the tab it was over, and takes the line away when the drag leaves the strip", () => {
  strip();
  fireEvent.dragStart(chip("c"), { dataTransfer: dataTransfer() });
  over("a", "left");
  fireEvent.dragLeave(chip("a"), { relatedTarget: document.body });
  expect(chip("a").className).not.toContain("before:w-0.5");
  over("b", "left");
  fireEvent.drop(chip("b"), { dataTransfer: dataTransfer() });
  fireEvent.dragEnd(chip("c"), { dataTransfer: dataTransfer() });
  expect(order()).toEqual(["a", "c", "b"]);
});

it("drops a tab on the right half of the last chip at the end of the strip, with the line drawn after it", () => {
  strip();
  fireEvent.dragStart(chip("b"), { dataTransfer: dataTransfer() });
  over("c", "right");
  expect(chip("c").className).toContain("after:w-0.5");
  fireEvent.drop(chip("c"), { dataTransfer: dataTransfer() });
  fireEvent.dragEnd(chip("b"), { dataTransfer: dataTransfer() });
  expect(order()).toEqual(["a", "c", "b"]);
});

it("drops a tab on the left half of the first chip at the front of the strip", () => {
  strip();
  fireEvent.dragStart(chip("c"), { dataTransfer: dataTransfer() });
  over("a", "left");
  fireEvent.drop(chip("a"), { dataTransfer: dataTransfer() });
  fireEvent.dragEnd(chip("c"), { dataTransfer: dataTransfer() });
  expect(order()).toEqual(["c", "a", "b"]);
});

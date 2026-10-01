import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { CommandPalette } from "@renderer/app/CommandPalette";
import { Shell } from "@renderer/app/Shell";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";
import type { ExplorerTab } from "@shared/types";

/**
 * Where the keyboard goes after a chord opens or picks a tab. The bodies are stand-ins: an editor
 * that goes with its tab (Monaco, a tree row) and a review with nothing that claims focus.
 */
vi.mock("@renderer/features/explorer/FileTab", () => ({
  FileTab: ({ tabId }: { tabId: string }) => <input aria-label={`Editor ${tabId}`} />,
}));
vi.mock("@renderer/features/sidebar/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@renderer/features/session/SessionPane", () => ({ SessionPane: () => null }));
// A terminal body as TerminalTab marks it (`terminal-tab.test.tsx` holds the marker itself).
vi.mock("@renderer/features/explorer/TerminalTab", () => ({
  TerminalTab: () => <div data-terminal-body><textarea aria-label="Terminal input" /></div>,
}));
vi.mock("@renderer/features/explorer/ReviewTab", () => ({ ReviewTab: () => <p>Review body</p> }));

// Windows and Linux: Control is the shell's there. The other tests press Meta and Control together.
vi.mock("@renderer/lib/platform", async (importOriginal) => ({ ...(await importOriginal<object>()), isMac: false,
  isPrimaryModifier: (event: KeyboardEvent) => event.ctrlKey,
}));

const PROJECT = { id: "focus-project", name: "Project", path: "/repo", createdAt: 0 };
const fileTab = (id: string, order: number): ExplorerTab =>
  ({ id, kind: "file", sessionId: "s1", projectId: PROJECT.id, order, root: null, panel: null, path: `${id}.ts` }) as ExplorerTab;
const reviewTab = (id: string, order: number): ExplorerTab =>
  ({ id, kind: "review", sessionId: "s1", projectId: PROJECT.id, order, scope: "turn" }) as ExplorerTab;

beforeEach(() => {
  useProjects.setState({ projects: [PROJECT], ready: true, activeId: PROJECT.id, draft: null });
  useExplorer.setState({ sessionId: "s1", projectId: PROJECT.id, root: null, ready: true, collapsed: false,
    tabs: [fileTab("f1", 0), reviewTab("r1", 1)], activeId: "f1" });
});

// The chords live on the shell (the pane is not mounted while collapsed).
const pane = () => render(<TooltipProvider><Shell /></TooltipProvider>);
const stripTab = (id: string) => document.querySelector(`[data-tab-strip] [data-tab="${id}"]`);

it("Mod+Shift+R from an editor hands focus to the new review's tab, not the page", async () => {
  pane();
  screen.getByRole("textbox", { name: "Editor f1" }).focus();
  fireEvent.keyDown(window, { key: "R", shiftKey: true, metaKey: true, ctrlKey: true });
  const opened = useExplorer.getState().activeId!;
  expect(useExplorer.getState().tabs.find((tab) => tab.id === opened)?.kind).toBe("review");
  await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  expect(document.activeElement).toBe(stripTab(opened));
});

it("Mod+2 from an editor hands focus to the picked tab, and Mod+1 back into its body's tab", async () => {
  pane();
  screen.getByRole("textbox", { name: "Editor f1" }).focus();
  fireEvent.keyDown(window, { key: "2", metaKey: true, ctrlKey: true });
  await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  expect(document.activeElement).toBe(stripTab("r1"));
  fireEvent.keyDown(window, { key: "1", metaKey: true, ctrlKey: true });
  await waitFor(() => expect(document.activeElement).toBe(stripTab("f1")));
});

it("Ctrl+W with the focus in a terminal is the shell's, not the strip's; Ctrl+K still reaches the palette", async () => {
  const terminal = { id: "t1", kind: "terminal", sessionId: "s1", projectId: PROJECT.id, order: 2, ptyId: null, cwd: null, readOnly: false } as ExplorerTab;
  useExplorer.setState({ tabs: [fileTab("f1", 0), terminal], activeId: "t1" });
  useUi.setState({ commandPaletteOpen: false });
  render(<TooltipProvider><Shell /><CommandPalette /></TooltipProvider>);
  await screen.findByLabelText("Terminal input");
  const input = screen.getByLabelText("Terminal input");
  input.focus();
  fireEvent.keyDown(input, { key: "w", ctrlKey: true });
  expect(useExplorer.getState().tabs.map((tab) => tab.id)).toEqual(["f1", "t1"]);
  fireEvent.keyDown(input, { key: "k", ctrlKey: true });
  expect(useUi.getState().commandPaletteOpen).toBe(true);
  // Out of the terminal the same chord closes the tab.
  fireEvent.keyDown(window, { key: "w", ctrlKey: true });
  expect(useExplorer.getState().tabs.map((tab) => tab.id)).toEqual(["f1"]);
});

it("Ctrl+` opens a terminal and reveals the pane while the explorer is collapsed, the default", () => {
  useExplorer.setState({ collapsed: true, tabs: [], activeId: null });
  pane();
  expect(document.getElementById("explorer")).toBeNull();
  fireEvent.keyDown(window, { key: "`", ctrlKey: true });
  expect(useExplorer.getState().tabs.map((tab) => tab.kind)).toEqual(["terminal"]);
  expect(useExplorer.getState().collapsed).toBe(false);
  expect(document.getElementById("explorer")).not.toBeNull();
});

it("a held Mod+T or Mod+W repeats nothing, and the repeat is still kept from the menu's Close", () => {
  useExplorer.setState({ tabs: [fileTab("f1", 0)], activeId: "f1" });
  pane();
  const held = (key: string) => {
    const event = new KeyboardEvent("keydown", { key, ctrlKey: true, repeat: true, bubbles: true, cancelable: true });
    window.dispatchEvent(event);
    return event;
  };
  expect(held("t").defaultPrevented).toBe(true);
  expect(useExplorer.getState().tabs).toHaveLength(1);
  expect(held("w").defaultPrevented).toBe(true);
  expect(useExplorer.getState().tabs).toHaveLength(1);
  fireEvent.keyDown(window, { key: "w", ctrlKey: true });
  expect(useExplorer.getState().tabs).toHaveLength(0);
  // Nothing left to close: the repeat still does not reach the menu, which would close the window.
  expect(held("w").defaultPrevented).toBe(true);
});

it("Ctrl+W and Mod+2 leave a collapsed explorer's hidden tabs alone, and the menu keeps the key", () => {
  const terminal = { id: "t1", kind: "terminal", sessionId: "s1", projectId: PROJECT.id, order: 1, ptyId: "pty-9", cwd: null, readOnly: false } as ExplorerTab;
  const tabs = [fileTab("f1", 0), terminal];
  useExplorer.setState({ collapsed: true, tabs, activeId: "t1" });
  const kill = vi.fn(async () => {});
  (window.textToCad.terminal as unknown as Record<string, unknown>).kill = kill;
  pane();
  const press = (key: string) => {
    const event = new KeyboardEvent("keydown", { key, ctrlKey: true, bubbles: true, cancelable: true });
    window.dispatchEvent(event);
    return event;
  };
  expect(press("w").defaultPrevented).toBe(false);
  expect(kill).not.toHaveBeenCalled();
  expect(useExplorer.getState().tabs).toEqual(tabs);
  expect(press("2").defaultPrevented).toBe(false);
  expect(useExplorer.getState().collapsed).toBe(true);
  expect(useExplorer.getState().activeId).toBe("t1");
});

it("Ctrl+Shift+R with the focus in a terminal still opens a review tab; the plain chords stay the shell's", async () => {
  const terminal = { id: "t1", kind: "terminal", sessionId: "s1", projectId: PROJECT.id, order: 2, ptyId: null, cwd: null, readOnly: false } as ExplorerTab;
  useExplorer.setState({ tabs: [fileTab("f1", 0), terminal], activeId: "t1" });
  pane();
  const input = await screen.findByLabelText("Terminal input");
  input.focus();
  fireEvent.keyDown(input, { key: "R", shiftKey: true, ctrlKey: true });
  expect(useExplorer.getState().tabs.map((tab) => tab.kind)).toEqual(["file", "terminal", "review"]);
  const before = useExplorer.getState().tabs.length;
  fireEvent.keyDown(input, { key: "t", ctrlKey: true });
  expect(useExplorer.getState().tabs).toHaveLength(before);
});

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Shell } from "@renderer/app/Shell";
import { useExplorer } from "@renderer/state/explorer";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings } from "@shared/types";

/**
 * The shell's landmarks and F6. The panes are stand-ins with each one's home: a session row in
 * the sidebar, the composer's box in the session, the strip's tab in the explorer — and each
 * with the `<header>` the real one draws.
 */
vi.mock("@renderer/features/sidebar/Sidebar", () => ({
  Sidebar: () => <><header>text-to-cad</header><button aria-current="page" type="button">Bracket</button></>,
}));
vi.mock("@renderer/features/session/SessionPane", () => ({
  SessionPane: () => <><header>Bracket<button aria-label="Toggle sidebar" type="button" /></header><div aria-label="Prompt" contentEditable data-composer-input role="textbox" suppressContentEditableWarning tabIndex={0} /></>,
}));
vi.mock("@renderer/features/explorer/ExplorerPane", () => ({
  useExplorerShortcuts: () => {},
  ExplorerPane: () => <div role="tablist"><div aria-selected data-tab="t1" role="tab" tabIndex={0}>part.step</div></div>,
}));

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1600 } as DOMRect);
  useSettings.setState({ settings: { ...defaultSettings(), layout: { ...defaultSettings().layout, sidebarCollapsed: false } }, ready: true } as never);
  useExplorer.setState({ sessionId: "s1", projectId: "p1", collapsed: false, width: 500 });
});
afterEach(() => vi.restoreAllMocks());

it("has one main (the session), and no pane's header is a banner", () => {
  render(<Shell />);
  expect(screen.getByRole("main")).toContainElement(screen.getByRole("textbox", { name: "Prompt" }));
  expect(screen.getByRole("complementary", { name: "Sidebar" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Explorer" })).toBeInTheDocument();
  // A <header> is a banner unless it is inside sectioning content or a landmark (HTML-AAM);
  // Testing Library does not scope it, so the rule is checked on the tree itself.
  const headers = [...document.querySelectorAll("header")];
  expect(headers).toHaveLength(2);
  expect(headers.filter((header) => !header.parentElement?.closest("main, aside, section, article, nav"))).toEqual([]);
});

it("moves focus sidebar → session → explorer → sidebar on F6, and back on Shift+F6", () => {
  render(<Shell />);
  const row = screen.getByRole("button", { name: "Bracket" });
  const composer = screen.getByRole("textbox", { name: "Prompt" });
  const tab = screen.getByRole("tab");
  row.focus();
  fireEvent.keyDown(row, { key: "F6" });
  expect(composer).toHaveFocus();
  fireEvent.keyDown(composer, { key: "F6" });
  expect(tab).toHaveFocus();
  fireEvent.keyDown(tab, { key: "F6" });
  expect(row).toHaveFocus();
  fireEvent.keyDown(row, { key: "F6", shiftKey: true });
  expect(tab).toHaveFocus();
});

it("names each pane separator and hints it without a native title", () => {
  render(<Shell />);
  const separators = screen.getAllByRole("separator");
  expect(separators.map((separator) => separator.getAttribute("aria-label"))).toEqual(["Resize the sidebar", "Resize the explorer"]);
  expect(separators.map((separator) => separator.getAttribute("aria-controls"))).toEqual(["sidebar", "explorer"]);
  for (const separator of separators) expect(separator).not.toHaveAttribute("title");
});

it("takes focus into the explorer when its chord (Ctrl+Shift+E off a Mac) opens it", async () => {
  useExplorer.setState({ collapsed: true });
  render(<Shell />);
  expect(screen.queryByRole("region", { name: "Explorer" })).toBeNull();
  const composer = screen.getByRole("textbox", { name: "Prompt" });
  composer.focus();
  fireEvent.keyDown(window, { key: "E", shiftKey: true, ctrlKey: true });
  await waitFor(() => expect(screen.getByRole("tab")).toHaveFocus());
});

it("hands focus to the session's sidebar toggle when Mod+B closes the sidebar it was in", async () => {
  render(<Shell />);
  const row = screen.getByRole("button", { name: "Bracket" });
  row.focus();
  // What runUiCommand's toggle-sidebar writes.
  act(() => { void useSettings.setState({ settings: { ...defaultSettings(), layout: { ...defaultSettings().layout, sidebarCollapsed: true } } } as never); });
  expect(screen.queryByRole("complementary", { name: "Sidebar" })).toBeNull();
  expect(screen.getByRole("button", { name: "Toggle sidebar" })).toHaveFocus();
});

it("hands focus to the sidebar's toggle when Enter on its separator closes the pane", async () => {
  render(<Shell />);
  const separator = screen.getAllByRole("separator")[0]!;
  separator.focus();
  fireEvent.keyDown(separator, { key: "Enter" });
  expect(screen.queryByRole("complementary", { name: "Sidebar" })).toBeNull();
  await waitFor(() => expect(screen.getByRole("button", { name: "Toggle sidebar" })).toHaveFocus());
});

it("reads a separator's value in words and draws its focus wider than the 1px line", () => {
  render(<Shell />);
  const [sidebar, explorer] = screen.getAllByRole("separator");
  expect(sidebar).toHaveAttribute("aria-valuetext", expect.stringMatching(/^sidebar \d+ pixels$/));
  expect(explorer).toHaveAttribute("aria-valuetext", "explorer 500 pixels");
  expect(sidebar!.className).toContain("focus-visible:shadow-");
});

import { renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@renderer/features/explorer/load-terminal", () => ({ loadTerminal: vi.fn(), preloadTerminal: vi.fn() }));

import { useExplorerShortcuts } from "@renderer/features/explorer/ExplorerPane";
import { useExplorer } from "@renderer/state/explorer";

const open = vi.fn(() => null);
beforeEach(() => {
  open.mockClear();
  useExplorer.setState({ sessionId: "session", projectId: "project", tabs: [], activeId: null, open } as never);
});

it("opens a terminal on Ctrl+` when the layout makes the backtick a dead key", () => {
  renderHook(() => useExplorerShortcuts());
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "Dead", code: "Backquote", ctrlKey: true, cancelable: true }));
  expect(open).toHaveBeenCalledWith("terminal");
});

it("leaves other Ctrl chords on that physical key alone", () => {
  renderHook(() => useExplorerShortcuts());
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "Dead", code: "Backquote", ctrlKey: true, shiftKey: true }));
  expect(open).not.toHaveBeenCalled();
});

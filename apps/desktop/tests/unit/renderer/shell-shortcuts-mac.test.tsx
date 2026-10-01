import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

import { Shell } from "@renderer/app/Shell";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";

const runUiCommand = vi.hoisted(() => vi.fn());
vi.mock("@renderer/state/bridge", async (importOriginal) => ({ ...(await importOriginal<object>()), runUiCommand }));
// A Mac, as the platform module reads it: the user agent, set before anything imports it.
vi.hoisted(() => {
  Object.defineProperty(navigator, "userAgent", {
    configurable: true,
    value: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
  });
});
vi.mock("@renderer/features/sidebar/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@renderer/features/session/SessionPane", () => ({ SessionPane: () => null }));

beforeEach(() => {
  runUiCommand.mockClear();
  useExplorer.setState({ sessionId: null, projectId: null, tabs: [], activeId: null, ready: true });
  useProjects.setState({ projects: [], ready: true, activeId: null, draft: null });
  useUi.setState({ route: "app", settingsSection: "general", commandPaletteOpen: false });
});
afterEach(cleanup);

/**
 * Option+B on a Mac types "∫", so `event.key` is not "b" and the renderer's own handler never saw
 * the chord (the menu accelerator did the work). The chord is the physical key.
 */
it("Cmd+Option+B toggles the explorer when Option has turned the key into an integral sign", () => {
  render(<Shell />);
  fireEvent.keyDown(window, { key: "∫", code: "KeyB", altKey: true, metaKey: true });
  expect(runUiCommand).toHaveBeenCalledWith({ command: "toggle-explorer" });
});

it("Cmd+B still toggles the sidebar, not the explorer", () => {
  render(<Shell />);
  fireEvent.keyDown(window, { key: "b", code: "KeyB", metaKey: true });
  expect(runUiCommand).toHaveBeenCalledWith({ command: "toggle-sidebar" });
  expect(runUiCommand).toHaveBeenCalledTimes(1);
});

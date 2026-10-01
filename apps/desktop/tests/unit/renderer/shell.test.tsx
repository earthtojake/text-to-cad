import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExplorerToggle } from "@renderer/app/PaneToggles";
import { Shell } from "@renderer/app/Shell";
import { SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { ExplorerPane } from "@renderer/features/explorer/ExplorerPane";
import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";

// The sidebar and the session have their own suites; for the shell only the
// row and its separators are under test. The explorer is the real one, since
// this file covers it too.
vi.mock("@renderer/features/sidebar/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@renderer/features/session/SessionPane", () => ({ SessionPane: () => null }));

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

beforeEach(() => {
  useExplorer.setState({ sessionId: null, projectId: null, tabs: [], activeId: null, ready: true });
  useProjects.setState({ projects: [], ready: true, activeId: null, draft: null });
  useUi.setState({ route: "app", settingsSection: "general", commandPaletteOpen: false });
});

/* The sidebar has its own suite: tests/unit/renderer/sidebar.test.tsx. */

describe("Explorer", () => {
  const PROJECT = { id: "p1", name: "text-to-cad", path: "/repo", createdAt: 0 };

  // The strip belongs to the selected session, grouped under its directory.
  const withSession = () => {
    useProjects.setState({
      projects: [PROJECT],
      ready: true,
      activeId: PROJECT.id,
    });
    useExplorer.setState({ sessionId: "s1", projectId: PROJECT.id, tabs: [], activeId: null, ready: true });
  };

  // The shell does not mount the pane without a project; the pane draws
  // nothing if it is mounted anyway. Either way there is no strip and no
  // control that offers to open one.
  it("draws nothing when there is no project to open anything from", () => {
    const { container } = wrap(<ExplorerPane />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no toggle for an explorer that is not there", () => {
    wrap(<ExplorerToggle />);
    expect(screen.queryByRole("button", { name: "Toggle explorer" })).toBeNull();
    cleanup();
    withSession();
    wrap(<ExplorerToggle />);
    expect(screen.getByRole("button", { name: "Toggle explorer" })).toBeInTheDocument();
  });

  it("opens a tab of each kind from the one `+` menu", async () => {
    const user = userEvent.setup();
    withSession();
    wrap(<ExplorerPane />);
    expect(screen.getByText("Nothing open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New tab" }));
    // Four kinds, each with the binding the keyboard actually answers to.
    // jsdom is not a Mac, so these print in the `Ctrl+` column.
    const rows: [string, string][] = [
      ["File", "Ctrl+T"],
      ["Review", "Ctrl+Shift+R"],
      ["Browser", "Ctrl+Shift+B"],
      ["Terminal", "Ctrl+`"],
    ];
    for (const [label, keys] of rows) {
      expect(screen.getByRole("menuitem", { name: new RegExp(`^${label}`) })).toHaveTextContent(keys);
    }
    // And no second control beside it any more.
    expect(screen.queryByRole("button", { name: "New tab of another kind" })).toBeNull();

    await user.click(screen.getByRole("menuitem", { name: /^File/ }));
    expect(useExplorer.getState().tabs).toHaveLength(1);
    // Hidden from the accessibility tree (Delete on the tab is its keyboard twin).
    expect(document.querySelector('button[aria-label="Close Open file…"]')).toBeInTheDocument();
  });

  it("opens a file tab on Mod+T without the menu", async () => {
    withSession();
    wrap(<Shell />);
    fireEvent.keyDown(window, { key: "t", metaKey: true, ctrlKey: true });
    expect(useExplorer.getState().tabs).toHaveLength(1);
    expect(useExplorer.getState().tabs[0]?.kind).toBe("file");
  });

  it("closes a tab from its close button", async () => {
    const user = userEvent.setup();
    withSession();
    wrap(<ExplorerPane />);
    await user.click(screen.getByRole("button", { name: "New tab" }));
    await user.click(screen.getByRole("menuitem", { name: /^File/ }));
    await user.click(document.querySelector<HTMLElement>('button[aria-label="Close Open file…"]')!);
    expect(useExplorer.getState().tabs).toHaveLength(0);
  });

  // The fullscreen explorer is gone: it was the one control in the app that
  // could take the session pane away, and the session is the app.
  it("offers no way to take the window from the session", () => {
    withSession();
    wrap(<ExplorerPane />);
    expect(screen.queryByRole("button", { name: "Expand explorer" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Restore layout" })).toBeNull();
  });

  // `+` is the last thing in the scrolling row rather than a control outside
  // it, so it reads as the end of the tabs — and `sticky right-0` is what
  // keeps it on screen once the row is longer than the pane.
  it("puts + after the last tab, pinned to the strip's right edge", async () => {
    const user = userEvent.setup();
    withSession();
    wrap(<ExplorerPane />);
    for (let i = 0; i < 3; i += 1) {
      await user.click(screen.getByRole("button", { name: "New tab" }));
      await user.click(screen.getByRole("menuitem", { name: /^File/ }));
    }
    const tablist = screen.getByRole("tablist");
    const plus = screen.getByRole("button", { name: "New tab" }).closest("[data-new-tab]");
    expect(plus).not.toBeNull();
    // A sibling that follows the tabs, not a child of the tablist.
    expect(tablist.contains(plus!)).toBe(false);
    expect(tablist.compareDocumentPosition(plus!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(plus).toHaveClass("sticky", "right-0");
    // The same scrolling row as the tabs, which is what makes it slide with
    // them until it reaches the edge.
    expect(plus!.parentElement).toBe(tablist.parentElement);
  });
});

describe("Shell separators", () => {
  // jsdom lays nothing out, so the row measures zero and every pane would
  // collapse for want of room. A laptop-sized row instead.
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1600 } as DOMRect);
    useExplorer.setState({ sessionId: "s1", projectId: "p1", collapsed: false, width: 600 });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.style.removeProperty("user-select");
  });

  const explorer = () => document.getElementById("explorer")!;
  const separator = () => document.querySelector<HTMLElement>("[data-separator=explorer]")!;

  // The arrow keys used to commit and then report a drag in the same batch,
  // so the shell kept drawing that drag's width for good: the next session's
  // explorer came up at this one's size.
  it("draws the stored width again after an arrow key", () => {
    render(<Shell />);
    expect(explorer().style.width).toBe("600px");
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    expect(useExplorer.getState().width).toBe(616);
    expect(explorer().style.width).toBe("616px");
    act(() => useExplorer.setState({ width: 500 }));
    expect(explorer().style.width).toBe("500px");
  });

  it("draws the stored width again after a drag that ends where it started", () => {
    render(<Shell />);
    fireEvent.pointerDown(separator(), { button: 0, clientX: 800 });
    fireEvent.pointerMove(window, { clientX: 760 });
    expect(explorer().style.width).toBe("640px");
    fireEvent.pointerMove(window, { clientX: 800 });
    fireEvent.pointerUp(window);
    act(() => useExplorer.setState({ width: 500 }));
    expect(explorer().style.width).toBe("500px");
  });

  // The separator can go mid-drag without the pointer coming up: the session
  // is switched, or the window narrows past what holds the pane.
  it("lets go of the gesture when the separator goes away mid-drag", () => {
    render(<Shell />);
    fireEvent.pointerDown(separator(), { button: 0, clientX: 800 });
    fireEvent.pointerMove(window, { clientX: 760 });
    expect(document.body.style.userSelect).toBe("none");
    act(() => useExplorer.setState({ sessionId: null }));
    expect(separator()).toBeNull();
    expect(document.body.style.userSelect).toBe("");
    act(() => useExplorer.setState({ sessionId: "s2", width: 500 }));
    expect(explorer().style.width).toBe("500px");
  });
});

describe("Settings", () => {
  it("renders the six pages in the nav", () => {
    wrap(<SettingsRoute />);
    for (const label of [
      "General",
      "Agents",
      "Appearance",
      "Git and worktrees",
      "Keyboard shortcuts",
      "About and updates",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("goes back to the app", async () => {
    const user = userEvent.setup();
    useUi.setState({ route: "settings" });
    wrap(<SettingsRoute />);
    await user.click(screen.getByRole("button", { name: /Back to app/ }));
    expect(useUi.getState().route).toBe("app");
  });
});

describe("SettingRow", () => {
  it("puts the description under the title and the control on the right", () => {
    wrap(
      <SettingCard title="App">
        <SettingRow control={<button type="button">Toggle</button>} description="Why" title="What" />
      </SettingCard>,
    );
    expect(screen.getByText("What")).toBeInTheDocument();
    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Toggle" })).toBeInTheDocument();
  });
});

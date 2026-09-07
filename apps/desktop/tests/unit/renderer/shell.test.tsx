import { describe, expect, it, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExplorerToggle } from "@renderer/app/PaneToggles";
import { SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { ExplorerPane } from "@renderer/features/explorer/ExplorerPane";
import { TooltipProvider } from "@renderer/components/ui/tooltip";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

beforeEach(() => {
  useExplorer.setState({ projectId: null, tabs: [], activeId: null, ready: true });
  useProjects.setState({ projects: [], ready: true, activeId: null, collapsed: new Set() });
  useUi.setState({ route: "app", settingsSection: "general", commandPaletteOpen: false });
});

describe("Sidebar", () => {
  it("offers a way in when there are no projects", () => {
    wrap(<Sidebar />);
    expect(screen.getByText("No projects yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add project" })).toBeInTheDocument();
  });

  it("lists projects with an empty session state under each", () => {
    useProjects.setState({
      projects: [{ id: "p1", name: "text-to-cad", path: "/repo", createdAt: 0 }],
      ready: true,
      activeId: "p1",
      collapsed: new Set(),
    });
    wrap(<Sidebar />);
    expect(screen.getByText("text-to-cad")).toBeInTheDocument();
    expect(screen.getByText("No sessions yet")).toBeInTheDocument();
  });
});

describe("Explorer", () => {
  const PROJECT = { id: "p1", name: "text-to-cad", path: "/repo", createdAt: 0 };

  // The strip belongs to a project (plan §3): there is nowhere to open a tab
  // without one, and no pane either.
  const withProject = () => {
    useProjects.setState({
      projects: [PROJECT],
      ready: true,
      activeId: PROJECT.id,
      collapsed: new Set(),
    });
    useExplorer.setState({ projectId: PROJECT.id, tabs: [], activeId: null, ready: true });
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
    withProject();
    wrap(<ExplorerToggle />);
    expect(screen.getByRole("button", { name: "Toggle explorer" })).toBeInTheDocument();
  });

  it("opens a tab of each kind from the one `+` menu", async () => {
    const user = userEvent.setup();
    withProject();
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
    expect(screen.getByRole("button", { name: "Close Untitled" })).toBeInTheDocument();
  });

  it("opens a file tab on Mod+T without the menu", async () => {
    withProject();
    wrap(<ExplorerPane />);
    fireEvent.keyDown(window, { key: "t", metaKey: true, ctrlKey: true });
    expect(useExplorer.getState().tabs).toHaveLength(1);
    expect(useExplorer.getState().tabs[0]?.kind).toBe("file");
  });

  it("closes a tab from its close button", async () => {
    const user = userEvent.setup();
    withProject();
    wrap(<ExplorerPane />);
    await user.click(screen.getByRole("button", { name: "New tab" }));
    await user.click(screen.getByRole("menuitem", { name: /^File/ }));
    await user.click(screen.getByRole("button", { name: "Close Untitled" }));
    expect(useExplorer.getState().tabs).toHaveLength(0);
  });

  // The fullscreen explorer is gone: it was the one control in the app that
  // could take the session pane away, and the session is the app.
  it("offers no way to take the window from the session", () => {
    withProject();
    wrap(<ExplorerPane />);
    expect(screen.queryByRole("button", { name: "Expand explorer" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Restore layout" })).toBeNull();
  });

  // `+` is the last thing in the scrolling row rather than a control outside
  // it, so it reads as the end of the tabs — and `sticky right-0` is what
  // keeps it on screen once the row is longer than the pane.
  it("puts + after the last tab, pinned to the strip's right edge", async () => {
    const user = userEvent.setup();
    withProject();
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

describe("Settings", () => {
  it("renders the six pages in the nav", () => {
    wrap(<SettingsRoute />);
    for (const label of [
      "General",
      "Agents",
      "Appearance",
      "Git & Worktrees",
      "Keyboard shortcuts",
      "About & Updates",
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

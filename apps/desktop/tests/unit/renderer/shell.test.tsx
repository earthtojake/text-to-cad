import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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
  useExplorer.setState({ tabs: [], activeId: null });
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
  it("starts empty and opens a file tab from the strip", async () => {
    const user = userEvent.setup();
    wrap(<ExplorerPane />);
    expect(screen.getByText("Nothing open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New tab" }));
    expect(useExplorer.getState().tabs).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Close Untitled" })).toBeInTheDocument();
  });

  it("closes a tab from its close button", async () => {
    const user = userEvent.setup();
    wrap(<ExplorerPane />);
    await user.click(screen.getByRole("button", { name: "New tab" }));
    await user.click(screen.getByRole("button", { name: "Close Untitled" }));
    expect(useExplorer.getState().tabs).toHaveLength(0);
  });
});

describe("Settings", () => {
  it("renders the seven pages in the nav", () => {
    wrap(<SettingsRoute />);
    for (const label of [
      "General",
      "Agents",
      "Appearance",
      "Git & Worktrees",
      "CAD Runtime",
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

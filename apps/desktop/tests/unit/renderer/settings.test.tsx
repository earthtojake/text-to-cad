/**
 * Settings' two pieces of logic that are not "read a value, write a value":
 * the search filter, and the shortcut table's platform glyphs.
 *
 * The search is tested through the real route rather than through
 * `matchesQuery` alone, because the thing worth asserting is the property the
 * design rests on: a query finds a row on a page nobody navigated to, and the
 * text it matched is the text the row prints.
 */
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@renderer/components/ui/tooltip";
import { SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { matchesQuery } from "@renderer/features/settings/search";
import { parseEnv, formatEnv } from "@renderer/features/settings/AgentDrawer";
import { agentIcon, agentIconIds } from "@renderer/lib/agent-icons";
import { SHORTCUTS, shortcutKeys, shortcutsIn } from "@renderer/lib/shortcuts";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings } from "@shared/types";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

beforeEach(() => {
  useUi.setState({ route: "settings", settingsSection: "general", commandPaletteOpen: false });
  useSettings.setState({ settings: defaultSettings(), ready: true });
});

describe("matchesQuery", () => {
  it("is true for an empty query, so an unsearched page shows every row", () => {
    expect(matchesQuery("", "Branch prefix")).toBe(true);
    expect(matchesQuery("   ", "Branch prefix")).toBe(true);
  });

  it("requires every term, in any order and anywhere in the row", () => {
    const title = "Auto-delete old worktrees";
    const description = "Remove the oldest worktrees once there are more than the limit.";
    expect(matchesQuery("worktree delete", title, description)).toBe(true);
    expect(matchesQuery("delete worktree", title, description)).toBe(true);
    expect(matchesQuery("worktree branch", title, description)).toBe(false);
  });

  it("ignores case and skips fields that are not there", () => {
    expect(matchesQuery("PREFIX", "Branch prefix", undefined)).toBe(true);
  });
});

describe("Settings search", () => {
  it("finds a row on a page that is not open, and hides the rest", async () => {
    const user = userEvent.setup();
    wrap(<SettingsRoute />);

    // General is the open page; the branch prefix lives on Git & Worktrees.
    expect(screen.queryByText("Branch prefix")).not.toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Search settings"), "branch prefix");

    expect(await screen.findByText("Branch prefix")).toBeVisible();
    // A row from another page, matching nothing, is gone rather than dimmed.
    expect(screen.queryByText("Launch at login")).not.toBeInTheDocument();
    // And the nav keeps only the pages that had a match.
    expect(screen.getByRole("button", { name: "Git & Worktrees" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About & Updates" })).not.toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    wrap(<SettingsRoute />);
    await user.type(screen.getByPlaceholderText("Search settings"), "zzzzz");
    expect(await screen.findByText("No matching settings.")).toBeInTheDocument();
  });

  it("clears the query when a page is chosen from the nav", async () => {
    const user = userEvent.setup();
    wrap(<SettingsRoute />);
    const box = screen.getByPlaceholderText("Search settings");
    await user.type(box, "branch");
    await user.click(await screen.findByRole("button", { name: "Git & Worktrees" }));
    expect(box).toHaveValue("");
    expect(useUi.getState().settingsSection).toBe("git");
  });
});

describe("SettingCard", () => {
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

describe("shortcuts", () => {
  it("prints macOS glyphs run together and everything else joined with +", () => {
    expect(shortcutKeys("Mod+K", true)).toBe("⌘K");
    expect(shortcutKeys("Mod+K", false)).toBe("Ctrl+K");
    expect(shortcutKeys("Mod+Alt+B", true)).toBe("⌘⌥B");
    expect(shortcutKeys("Mod+Alt+B", false)).toBe("Ctrl+Alt+B");
    expect(shortcutKeys("Shift+Enter", true)).toBe("⇧⏎");
    expect(shortcutKeys("Escape", false)).toBe("Esc");
  });

  it("covers every group and gives each shortcut a unique id", () => {
    expect(shortcutsIn("Application").length).toBeGreaterThan(0);
    expect(shortcutsIn("Session").length).toBeGreaterThan(0);
    expect(shortcutsIn("Explorer").length).toBeGreaterThan(0);
    expect(new Set(SHORTCUTS.map((shortcut) => shortcut.id)).size).toBe(SHORTCUTS.length);
  });
});

describe("agent icons", () => {
  it("has the registry's mark for the agents the plan names", () => {
    for (const id of ["claude-code", "codex", "gemini-cli", "github-copilot"]) {
      expect(agentIconIds(), id).toContain(id);
    }
    // Two agents the ACP registry has no logo for come from their vendors:
    // Kiro's SVG from kiro.dev, Hermes's raster favicon wrapped by hand.
    expect(agentIconIds()).toContain("kiro");
    expect(agentIconIds()).toContain("hermes");
    expect(agentIcon("hermes")).toContain("<image");
    expect(agentIcon("not-an-agent")).toBeNull();
    expect(agentIcon(null)).toBeNull();
  });

  it("hands back scalable markup drawn in currentColor", () => {
    const svg = agentIcon("codex") ?? "";
    expect(svg).toMatch(/^<svg\b/);
    expect(svg).toContain('width="100%"');
    // currentColor is why these are inlined rather than loaded as images: the
    // mark takes the colour of the text beside it, in either theme.
    expect(svg).toContain("currentColor");
    // And nothing that could run or fetch got committed.
    expect(svg).not.toMatch(/<script|\son\w+=/i);
  });
});

describe("the per-agent environment editor", () => {
  it("round-trips KEY=value lines", () => {
    expect(parseEnv("A=1\nB=two words")).toEqual({ A: "1", B: "two words" });
    expect(formatEnv({ A: "1", B: "2" })).toBe("A=1\nB=2");
  });

  it("ignores blank lines, comments and lines with no name", () => {
    expect(parseEnv("\n# a comment\n=novalue\nOK=yes\n")).toEqual({ OK: "yes" });
  });

  it("keeps everything after the first = , which is where tokens live", () => {
    expect(parseEnv("TOKEN=a=b=c")).toEqual({ TOKEN: "a=b=c" });
  });
});

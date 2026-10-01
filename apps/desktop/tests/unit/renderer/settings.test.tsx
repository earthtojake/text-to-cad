/**
 * Settings' two pieces of logic that are not "read a value, write a value":
 * the search filter, and the shortcut table's platform glyphs.
 *
 * The search is tested through the real route rather than through
 * `matchesQuery` alone, because the thing worth asserting is the property the
 * design rests on: a query finds a row on a page nobody navigated to, and the
 * text it matched is the text the row prints.
 */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { AgentsPage } from "@renderer/features/settings/pages/AgentsPage";
import { GitPage } from "@renderer/features/settings/pages/GitPage";
import { ShortcutsPage } from "@renderer/features/settings/pages/ShortcutsPage";
import { SettingsSearchProvider, matchesQuery } from "@renderer/features/settings/search";
import { AgentDrawer, authLabel, parseEnv, formatEnv } from "@renderer/features/settings/AgentDrawer";
import { agentIcon, agentIconIds } from "@renderer/lib/agent-icons";
import { SHORTCUTS, shortcutKeys, shortcutsIn } from "@renderer/lib/shortcuts";
import { useAgents } from "@renderer/state/agents";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import type { AgentStatus } from "@shared/agents";
import { defaultSettings, type Settings } from "@shared/types";

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

    // General is the open page; the branch prefix lives on Git and worktrees.
    expect(screen.queryByText("Branch prefix")).not.toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Search settings"), "branch prefix");

    expect(await screen.findByText("Branch prefix")).toBeVisible();
    // A row from another page, matching nothing, is gone rather than dimmed.
    expect(screen.queryByText("Launch at login")).not.toBeInTheDocument();
    // And the nav keeps only the pages that had a match.
    expect(screen.getByRole("button", { name: "Git and worktrees" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About and updates" })).not.toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    wrap(<SettingsRoute />);
    await user.type(screen.getByPlaceholderText("Search settings"), "zzzzz");
    expect(await screen.findByRole("status")).toHaveTextContent("No matching settings.");
  });

  it("forgets the last search's pages: General is not in the nav for a query it has nothing for", async () => {
    wrap(<SettingsRoute />);
    const box = screen.getByPlaceholderText("Search settings");
    // Whole queries at once: every page is mounted while one is active, and
    // typing them a letter at a time is seconds of re-renders.
    fireEvent.change(box, { target: { value: "telemetry" } });
    expect(await screen.findByRole("button", { name: "General" })).toBeInTheDocument();
    fireEvent.change(box, { target: { value: "" } });
    fireEvent.change(box, { target: { value: "worktree" } });
    expect(await screen.findByRole("button", { name: "Git and worktrees" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "General" })).not.toBeInTheDocument();
    // Not an empty heading either: the page itself is hidden.
    expect(screen.queryByRole("heading", { name: "General" })).not.toBeInTheDocument();
  });

  it("clears the query when a page is chosen from the nav", async () => {
    const user = userEvent.setup();
    wrap(<SettingsRoute />);
    const box = screen.getByPlaceholderText("Search settings");
    await user.type(box, "branch");
    await user.click(await screen.findByRole("button", { name: "Git and worktrees" }));
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

describe("the shortcuts page", () => {
  it("names the toast chord, which no row holds", () => {
    wrap(<ShortcutsPage />);
    expect(screen.getByText("Toasts: ⌘⌥T on macOS, Ctrl+Shift+T elsewhere.")).toBeInTheDocument();
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

describe("the drawer's sign-in label", () => {
  it("speaks the agent rows' words: Not signed in when signed out, only what detection knows when unknown", () => {
    expect(authLabel({ auth: "unauthenticated", installed: true })).toBe("Not signed in");
    expect(authLabel({ auth: "unknown", installed: true })).toBe("Installed");
    expect(authLabel({ auth: "unknown", installed: false })).toBe("Not installed");
    expect(authLabel({ auth: "authenticated", installed: true })).toBe("Signed in");
  });
});

describe("Settings' visual fixes", () => {
  it("keeps the search glyph clear of the text: the left padding beats the Input's own px-3", () => {
    wrap(<SettingsRoute />);
    const box = screen.getByPlaceholderText("Search settings");
    // `cn` keeps `px-3` beside a plain `pl-8` (they set different properties)
    // and the built sheet orders `px-3` later, so only the important form
    // wins regardless of order.
    expect(box.className.split(/\s+/)).toContain("pl-8!");
    expect(box.className.split(/\s+/)).not.toContain("pl-8");
  });

  it("names the OS banner switch for what it does, and draws the off track's edge", () => {
    useSettings.setState({ settings: { ...defaultSettings(), notificationOsBanners: false }, ready: true });
    wrap(<SettingsRoute />);
    const banners = screen.getByRole("switch", { name: "System banners" });
    expect(banners).toHaveAttribute("data-state", "unchecked");
    expect(banners.className).toContain("data-[state=unchecked]:border-foreground/25");
    expect(screen.queryByText("OS notifications")).toBeNull();
  });
});

describe("the Settings nav", () => {
  it("says which page is on screen with aria-current, not only a tint", async () => {
    const user = userEvent.setup();
    useUi.setState({ route: "settings", settingsSection: "general" });
    wrap(<SettingsRoute />);
    const nav = screen.getByRole("navigation");
    expect(within(nav).getByRole("button", { name: "General" })).toHaveAttribute("aria-current", "page");
    await user.click(within(nav).getByRole("button", { name: "Appearance" }));
    expect(within(nav).getByRole("button", { name: "Appearance" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("button", { name: "General" })).not.toHaveAttribute("aria-current");
  });
});

describe("the agent drawer's sign-in", () => {
  const agent = (auth: "authenticated" | "unauthenticated") =>
    ({
      id: "claude-code",
      name: "Claude Code",
      description: "",
      websiteUrl: "https://example.com",
      docsUrl: "https://example.com",
      icon: null,
      installed: true,
      binaryPath: "/bin/claude",
      version: "1.0.0",
      auth,
      authMethods: [
        { type: "cli-login", label: "Sign in with your Anthropic account" },
        { type: "api-key", label: "Anthropic API key", envVars: ["ANTHROPIC_API_KEY"] },
      ],
      capabilities: {},
      install: { macos: [], windows: [], linux: [] },
      launch: { command: "npx", args: [], env: {} },
      skillRoots: "native",
    }) as unknown as AgentStatus;

  it("signed in: the status, one secondary Sign in again, and the API key folded away", async () => {
    wrap(<AgentDrawer agent={agent("authenticated")} onOpenChange={() => {}} open platform="macos" />);
    expect(await screen.findByText("Signed in")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in again" })).toBeInTheDocument();
    expect(screen.queryByText("Sign in with your Anthropic account")).toBeNull();
    const disclosure = screen.getByText("Use an API key instead").closest("details")!;
    expect(disclosure.open).toBe(false);
  });

  it("hints extra arguments without another agent's model in them", async () => {
    wrap(<AgentDrawer agent={agent("authenticated")} onOpenChange={() => {}} open platform="macos" />);
    const extra = await screen.findByLabelText("Extra arguments");
    expect(extra.getAttribute("placeholder")).not.toMatch(/gpt|model/i);
  });

  it("signed out: the method's words beside a primary Sign in", async () => {
    wrap(<AgentDrawer agent={agent("unauthenticated")} onOpenChange={() => {}} open platform="macos" />);
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Sign in with your Anthropic account")).toBeInTheDocument();
  });
});

describe("the Agents page's rows", () => {
  const opencode = {
    id: "opencode",
    name: "OpenCode",
    description: "`opencode acp` serves ACP",
    websiteUrl: "https://example.com",
    docsUrl: "https://example.com/docs",
    icon: null,
    installed: false,
    binaryPath: null,
    version: null,
    auth: "unknown",
    authMethods: [],
    capabilities: {},
    install: { macos: [], windows: [], linux: [] },
    launch: { command: "opencode", args: ["acp"], env: {} },
    skillRoots: "native",
  } as unknown as AgentStatus;

  beforeEach(() => {
    vi.mocked(window.textToCad.agents.list).mockResolvedValue([opencode]);
    vi.mocked(window.textToCad.shell.openExternal).mockClear();
    useAgents.setState({ agents: [opencode], ready: true, loadError: null });
  });

  it("Enter on the focused docs button opens the docs, not the drawer behind it", async () => {
    const user = userEvent.setup();
    wrap(<AgentsPage />);
    const docs = await screen.findByRole("button", { name: "OpenCode documentation" });
    docs.focus();
    await user.keyboard("{Enter}");
    expect(window.textToCad.shell.openExternal).toHaveBeenCalledWith({ url: "https://example.com/docs" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("draws a description's backticks as code, in the row and the drawer", async () => {
    const user = userEvent.setup();
    wrap(<AgentsPage />);
    const row = await screen.findByRole("button", { name: "OpenCode" });
    expect(row).not.toHaveTextContent("`");
    expect(row.querySelector("code")).toHaveTextContent("opencode acp");
    await user.click(row);
    const drawer = await screen.findByRole("dialog");
    expect(drawer).not.toHaveTextContent("`");
    expect(drawer.querySelector("code")).toHaveTextContent("opencode acp");
  });

  it("keeps Docs and Install beside the row's button, not inside it (nested-interactive)", async () => {
    wrap(<AgentsPage />);
    const row = await screen.findByRole("button", { name: "OpenCode" });
    expect(document.querySelectorAll("[role=button] button, button button")).toHaveLength(0);
    expect(row).toHaveAccessibleDescription("`opencode acp` serves ACP".replace(/`/g, ""));
    for (const name of ["OpenCode documentation", "Install OpenCode…"]) {
      expect(row.contains(screen.getByRole("button", { name }))).toBe(false);
    }
  });

  it("Escape closes the drawer and hands focus back to the row that opened it", async () => {
    const user = userEvent.setup();
    wrap(<AgentsPage />);
    const row = await screen.findByRole("button", { name: "OpenCode" });
    row.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    expect(row).toHaveFocus();
  });

  it("Enter on the row itself still opens the drawer", async () => {
    const user = userEvent.setup();
    wrap(<AgentsPage />);
    (await screen.findByRole("button", { name: "OpenCode" })).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("shows a pinned adapter's version beside the CLI's, in the row and the drawer", async () => {
    const claude = {
      ...opencode,
      id: "claude-code",
      name: "Claude Code",
      installed: true,
      binaryPath: "/bin/claude",
      version: "2.1.261",
      auth: "authenticated",
      adapter: { package: "@agentclientprotocol/claude-agent-acp", version: "0.84.0" },
    } as unknown as AgentStatus;
    useAgents.setState({ agents: [claude], ready: true, loadError: null });
    vi.mocked(window.textToCad.agents.list).mockResolvedValue([claude]);
    const user = userEvent.setup();
    wrap(<AgentsPage />);
    const row = await screen.findByRole("button", { name: "Claude Code" });
    expect(row).toHaveTextContent("v2.1.261 · adapter 0.84.0");
    await user.click(row);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Found at /bin/claude · v2.1.261 · adapter 0.84.0");
  });
});

describe("a settings text field", () => {
  it("keeps what is being typed when an earlier write's answer lands late", async () => {
    const replies: ((settings: Settings) => void)[] = [];
    vi.mocked(window.textToCad.settings.set).mockImplementation(
      () => new Promise<Settings>((resolve) => replies.push(resolve)),
    );
    const user = userEvent.setup();
    wrap(<GitPage />);
    const box = screen.getByRole("textbox", { name: "Commit instructions" });
    await user.type(box, "a");
    await user.tab();
    await user.click(box);
    await user.type(box, "b");
    expect(box).toHaveValue("ab");
    // The answer to the write of "a" arrives while "ab" is still being edited.
    await act(async () => {
      replies[0]!({ ...defaultSettings(), commitInstructions: "a" });
    });
    expect(box).toHaveValue("ab");
  });

  it("writes a finished edit once, not once per keystroke", async () => {
    vi.mocked(window.textToCad.settings.set).mockReset();
    vi.mocked(window.textToCad.settings.set).mockImplementation(async (patch) => ({ ...defaultSettings(), ...(patch as Partial<Settings>) }));
    const user = userEvent.setup();
    wrap(<GitPage />);
    await user.type(screen.getByRole("textbox", { name: "Branch prefix" }), "{Control>}a{/Control}me/{Enter}");
    expect(window.textToCad.settings.set).toHaveBeenCalledTimes(1);
    expect(window.textToCad.settings.set).toHaveBeenCalledWith({ branchPrefix: "me/" });
  });
});

describe("the branch prefix row", () => {
  it("says why git would refuse a prefix, and does not write it", async () => {
    vi.mocked(window.textToCad.settings.set).mockReset();
    const user = userEvent.setup();
    wrap(<GitPage />);
    const box = screen.getByRole("textbox", { name: "Branch prefix" });
    await user.clear(box);
    await user.type(box, "a b/{Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("Git refuses spaces in a branch name.");
    expect(box).toHaveAccessibleDescription(/^Git refuses spaces in a branch name\./);
    await user.tab();
    expect(window.textToCad.settings.set).not.toHaveBeenCalled();
  });
});

describe("the Agents page under the Settings search", () => {
  const agent = (id: string, name: string) =>
    ({
      id,
      name,
      description: `${name} agent`,
      websiteUrl: "https://example.com",
      docsUrl: "https://example.com/docs",
      icon: null,
      installed: true,
      binaryPath: `/bin/${id}`,
      version: "1.0.0",
      auth: "authenticated",
      authMethods: [],
      capabilities: {},
      install: { macos: [], windows: [], linux: [] },
      launch: { command: id, args: [], env: {} },
      skillRoots: "native",
    }) as unknown as AgentStatus;

  it("counts the rows the search leaves, not the ones it hides", async () => {
    const agents = [agent("codex", "Codex"), agent("claude-code", "Claude Code"), agent("goose", "Goose"), agent("amp", "Amp")];
    vi.mocked(window.textToCad.agents.list).mockResolvedValue(agents);
    useAgents.setState({ agents, ready: true, loadError: null });
    wrap(
      <SettingsSearchProvider query="codex" reportCard={() => {}} section="agents">
        <AgentsPage />
      </SettingsSearchProvider>,
    );
    expect(await screen.findByText("Installed (1)")).toBeInTheDocument();
    expect(screen.getAllByText(/^(Codex|Claude Code|Goose|Amp)$/)).toHaveLength(1);
  });
});

describe("the Agents page when the list cannot be read", () => {
  it("shows the handler's words in an alert, not Electron's invoke wrapper", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(window.textToCad.agents.list).mockRejectedValue(
      new Error("Error invoking remote method 'text-to-cad:agents.list': Error: the registry is unreadable"),
    );
    useAgents.setState({ agents: [], ready: false, loadError: null });
    wrap(<AgentsPage />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("data-slot", "alert");
    expect(alert).toHaveTextContent("the registry is unreadable");
    expect(alert).not.toHaveTextContent(/invoking remote method/);
    logged.mockRestore();
  });
});

describe("the worktree keep limit", () => {
  it("is off, and says why, while auto-delete is off", () => {
    useSettings.setState({ settings: { ...defaultSettings(), autoDeleteWorktrees: false }, ready: true });
    wrap(<GitPage />);
    expect(screen.getByRole("combobox", { name: "Keep limit" })).toBeDisabled();
    expect(screen.getByText(/Nothing is swept while Auto-delete old worktrees is off/)).toBeInTheDocument();
  });

  it("shows a stored limit that is not a preset, rather than a blank select", () => {
    useSettings.setState({ settings: { ...defaultSettings(), autoDeleteWorktrees: true, worktreeKeepLimit: 7 }, ready: true });
    wrap(<GitPage />);
    expect(screen.getByRole("combobox", { name: "Keep limit" })).toHaveTextContent("Keep 7");
  });

  it("is on once auto-delete is", () => {
    useSettings.setState({ settings: { ...defaultSettings(), autoDeleteWorktrees: true }, ready: true });
    wrap(<GitPage />);
    expect(screen.getByRole("combobox", { name: "Keep limit" })).toBeEnabled();
  });

  it("says a worktree with unsaved work counts toward the limit and is then kept", () => {
    useSettings.setState({ settings: { ...defaultSettings(), autoDeleteWorktrees: true }, ready: true });
    wrap(<GitPage />);
    expect(
      screen.getByText("How many idle worktrees per project the sweep keeps. In-use and locked ones are not counted; one with unsaved work is counted, then kept."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/unsaved ones are not counted/)).toBeNull();
  });
});

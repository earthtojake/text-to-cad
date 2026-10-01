/**
 * The palette's shape: one prompt string for the box and the dialog's
 * description, a Create group holding every New-tab kind, and a dialog
 * anchored near the top rather than centred (a centred one jumps as the list
 * filters).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import { COMMAND_PALETTE_LABEL, COMMAND_PALETTE_PROMPT, CommandPalette } from "@renderer/app/CommandPalette";
import { useOnboarding } from "@renderer/state/onboarding";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings, type Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

beforeEach(() => {
  useUi.setState({ route: "app", commandPaletteOpen: true, commandPaletteQuery: "" });
});

describe("the command palette", () => {
  it("says so in a toast when the folder chooser fails", async () => {
    const user = userEvent.setup();
    vi.mocked(window.textToCad.projects.add).mockRejectedValue(new Error("the chooser is unavailable"));
    render(<CommandPalette />);
    await user.click(screen.getByRole("option", { name: /Open folder/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not open that folder", {
        description: "the chooser is unavailable",
      }),
    );
  });

  it("opens empty after Settings was opened from it with something typed", () => {
    useUi.getState().setCommandPaletteQuery("x");
    useUi.getState().openSettings();
    expect(useUi.getState().commandPaletteQuery).toBe("");
  });

  it("uses one string for its placeholder and its description", () => {
    render(<CommandPalette />);
    expect(screen.getByPlaceholderText(COMMAND_PALETTE_PROMPT)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(COMMAND_PALETTE_PROMPT);
  });

  it("is anchored near the top, not centred", () => {
    render(<CommandPalette />);
    const classes = screen.getByRole("dialog").className.split(/\s+/);
    expect(classes).toContain("top-[20%]");
    expect(classes).toContain("translate-y-0");
    expect(classes).not.toContain("top-[50%]");
    expect(classes).not.toContain("translate-y-[-50%]");
  });

  it("finds every New-tab kind under Create when a session is open", async () => {
    useSessions.setState({ activeId: "s1" });
    const user = userEvent.setup();
    render(<CommandPalette />);
    await user.type(screen.getByPlaceholderText(COMMAND_PALETTE_PROMPT), "new");
    for (const name of ["New session", "New file tab", "New review tab", "New terminal", "New browser tab", "New drawing"]) {
      expect(screen.getByRole("option", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Create")).toBeInTheDocument();
  });

  it("draws no Sessions heading over an empty group", () => {
    // Nothing to list, or only what is archived: a heading with no rows under it.
    useSessions.setState({ sessions: [], activeId: null });
    const { unmount } = render(<CommandPalette />);
    expect(screen.queryByText("Sessions")).toBeNull();
    expect(screen.getByText("Projects")).toBeTruthy();
    unmount();
    const archived = { id: "s2", projectId: "/p", title: "Old", archived: true } as unknown as Session;
    useSessions.setState({ sessions: [archived], activeId: null });
    render(<CommandPalette />);
    expect(screen.queryByText("Sessions")).toBeNull();
  });

  it("leaves Settings for a session chosen behind it, and the welcome too", async () => {
    const session = {
      id: "s1", projectId: "/p", agentId: "claude-code", cwd: "/p", gitMode: "none", title: "Bracket",
      titleSource: "prompt", createdAt: 1, updatedAt: 1, status: "idle", acpSessionId: null,
      changedFiles: 0, insertions: 0, deletions: 0, archived: false, pinned: false,
      sessionHead: null, turnHead: null,
    } as unknown as Session;
    const patch = vi.fn(async () => undefined);
    useSessions.setState({ sessions: [session], activeId: null });
    useSettings.setState({ settings: { ...defaultSettings, onboardingCompleted: false }, patch } as never);
    useOnboarding.setState({ enabled: true });
    useUi.setState({ route: "settings" });
    const user = userEvent.setup();
    render(<CommandPalette />);
    await user.click(screen.getByRole("option", { name: /Bracket/ }));
    expect(useUi.getState().route).toBe("app");
    expect(patch).toHaveBeenCalledWith({ onboardingCompleted: true });
  });

  it("leaves Settings for a view toggle, but a toggle does not skip the welcome", async () => {
    const patch = vi.fn(async () => undefined);
    useSettings.setState({ settings: { ...defaultSettings, onboardingCompleted: false }, patch, setLayout: vi.fn() } as never);
    useOnboarding.setState({ enabled: true });
    useUi.setState({ route: "settings" });
    const user = userEvent.setup();
    render(<CommandPalette />);
    await user.click(screen.getByRole("option", { name: "Toggle sidebar" }));
    expect(useUi.getState().route).toBe("app");
    expect(patch).not.toHaveBeenCalled();
  });

  it("hands focus back to what had it when Escape closes it, not to the page", async () => {
    useUi.setState({ commandPaletteOpen: false });
    const user = userEvent.setup();
    render(<><div aria-label="Composer" contentEditable role="textbox" tabIndex={0} /><CommandPalette /></>);
    const composer = screen.getByRole("textbox", { name: "Composer" });
    composer.focus();
    act(() => useUi.getState().setCommandPaletteOpen(true));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveFocus());
    await user.keyboard("{Escape}");
    await waitFor(() => expect(useUi.getState().commandPaletteOpen).toBe(false));
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    expect(composer).toHaveFocus();
  });

  it("names its box, keeps separators out of the listbox, and its title inside the dialog", () => {
    const view = render(<CommandPalette />);
    expect(screen.getByRole("combobox")).toHaveAccessibleName(COMMAND_PALETTE_LABEL);
    expect(document.querySelectorAll("[role=listbox] [role=separator]")).toHaveLength(0);
    expect(screen.getByRole("dialog")).toContainElement(screen.getByText("Command palette"));
    // Shut, it leaves no heading in the page.
    act(() => useUi.getState().setCommandPaletteOpen(false));
    view.rerender(<CommandPalette />);
    expect(screen.queryByText("Command palette")).toBeNull();
  });
});

describe("what the palette searches", () => {
  const thread = (id: string, title: string, projectId = "p1") =>
    ({ id, projectId, title, archived: false }) as unknown as Session;

  it("does not match a session by the hex of its id", async () => {
    const user = userEvent.setup();
    useSessions.setState({ sessions: [thread("0dead0beef", "Alpha"), thread("0f00d0cafe", "Beta")], activeId: null });
    render(<CommandPalette />);
    await user.type(screen.getByRole("combobox"), "dead");
    expect(screen.queryByText("Alpha")).toBeNull();
    expect(screen.queryByText("Beta")).toBeNull();
  });

  it("still finds a session by its title, and two of one title stay two rows", async () => {
    const user = userEvent.setup();
    useSessions.setState({ sessions: [thread("a1", "New session"), thread("b2", "New session"), thread("c3", "Beta")], activeId: null });
    render(<CommandPalette />);
    const group = () => within(screen.getByText("Sessions").closest("[cmdk-group]") as HTMLElement);
    expect(group().getAllByText("New session")).toHaveLength(2);
    await user.type(screen.getByRole("combobox"), "beta");
    expect(group().getByText("Beta")).toBeInTheDocument();
    expect(group().queryByText("New session")).toBeNull();
  });

  it("scores a project on its name, not its path", async () => {
    const user = userEvent.setup();
    useProjects.setState({ projects: [{ id: "p1", name: "bracket", path: "/Users/amy/code/bracket", createdAt: 0 }] } as never);
    useSessions.setState({ sessions: [thread("a1", "Alpha")], activeId: null });
    render(<CommandPalette />);
    await user.type(screen.getByRole("combobox"), "code");
    expect(screen.queryByText("/Users/amy/code/bracket")).toBeNull();
  });
});

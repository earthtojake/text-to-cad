import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "@renderer/app/App";
import { useOnboarding } from "@renderer/state/onboarding";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings } from "@shared/types";

/**
 * The window's three routes are each a full page, and each has one `main`. Settings and the
 * welcome used to be landmark-free divs; leaving Settings dropped focus on the page.
 * The shell's panes are stand-ins (as in shell-landmarks.test.tsx): the routes are real.
 */
vi.mock("@renderer/features/sidebar/Sidebar", () => ({ Sidebar: () => <header>text-to-cad</header> }));
vi.mock("@renderer/features/session/SessionPane", () => ({
  SessionPane: () => <div aria-label="Prompt" contentEditable data-composer-input role="textbox" suppressContentEditableWarning tabIndex={0} />,
}));
vi.mock("@renderer/features/explorer/ExplorerPane", () => ({ useExplorerShortcuts: () => {}, ExplorerPane: () => null }));
vi.mock("@renderer/app/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@renderer/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@renderer/state/bridge", () => ({ hydrate: vi.fn(async () => undefined), subscribeToMain: () => () => undefined }));

function settled(overrides: Partial<ReturnType<typeof defaultSettings>> = {}) {
  useSettings.setState({ settings: { ...defaultSettings(), onboardingCompleted: true, ...overrides }, ready: true } as never);
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1600 } as DOMRect);
  useUi.setState({ route: "app", settingsSection: "general", commandPaletteOpen: false });
  useOnboarding.setState({ enabled: false });
  settled();
});
afterEach(() => vi.restoreAllMocks());

describe("App's routes", () => {
  it("has exactly one main on the shell, on Settings and on the welcome", () => {
    const shell = render(<App />);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    shell.unmount();

    useUi.setState({ route: "settings" });
    const settings = render(<App />);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    settings.unmount();

    useUi.setState({ route: "app" });
    useOnboarding.setState({ enabled: true });
    settled({ onboardingCompleted: false });
    render(<App />);
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });

  it("returns focus to the composer when Settings closes, not to the page", async () => {
    const user = userEvent.setup();
    useUi.setState({ route: "settings" });
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Back to app" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Prompt" })).toHaveFocus());
  });
});

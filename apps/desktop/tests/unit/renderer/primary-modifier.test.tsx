/**
 * On macOS the app's shortcuts are Command's, never Control's: in a text field
 * Ctrl+K kills to the end of the line and Ctrl+N moves down one, and neither
 * may open the palette or leave the session. jsdom is not a Mac, so the user
 * agent is set before the platform module reads it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";

vi.hoisted(() => {
  Object.defineProperty(navigator, "userAgent", {
    configurable: true,
    value: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
  });
});

vi.mock("@renderer/features/session/NewSession", () => ({ NewSession: () => null }));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/SessionView", () => ({ SessionView: () => null }));

import { CommandPalette } from "@renderer/app/CommandPalette";
import { SessionPane } from "@renderer/features/session/SessionPane";
import { useSettingsShortcuts } from "@renderer/hooks/use-settings-shortcuts";
import { isPrimaryModifier } from "@renderer/lib/platform";
import { useSessions } from "@renderer/state/sessions";
import { useUi } from "@renderer/state/ui";

beforeEach(() => {
  useUi.setState({ route: "app", commandPaletteOpen: false, commandPaletteQuery: "" });
});

describe("the primary modifier on macOS", () => {
  it("is Command and not Control", () => {
    expect(isPrimaryModifier(new KeyboardEvent("keydown", { metaKey: true }))).toBe(true);
    expect(isPrimaryModifier(new KeyboardEvent("keydown", { ctrlKey: true }))).toBe(false);
  });

  it("opens the palette on Cmd+K and not on Ctrl+K", () => {
    render(<CommandPalette />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(useUi.getState().commandPaletteOpen).toBe(false);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(useUi.getState().commandPaletteOpen).toBe(true);
  });

  it("leaves the session on Cmd+N and not on Ctrl+N", () => {
    const setActive = vi.fn();
    useSessions.setState({ setActive });
    render(<SessionPane />);
    fireEvent.keyDown(window, { key: "n", ctrlKey: true });
    expect(setActive).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "n", metaKey: true });
    expect(setActive).toHaveBeenCalledWith(null);
  });

  it("opens Settings on Cmd+, and not on Ctrl+,", () => {
    const Probe = () => {
      useSettingsShortcuts();
      return null;
    };
    render(<Probe />);
    fireEvent.keyDown(window, { key: ",", ctrlKey: true });
    expect(useUi.getState().route).toBe("app");
    fireEvent.keyDown(window, { key: ",", metaKey: true });
    expect(useUi.getState().route).toBe("settings");
  });
});

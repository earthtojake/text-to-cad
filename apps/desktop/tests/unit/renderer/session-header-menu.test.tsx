import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";

import { SessionHeader } from "@renderer/features/session/SessionHeader";
import { useAcp } from "@renderer/state/acp";
import { useSessions } from "@renderer/state/sessions";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

const SESSION = { id: "s1", projectId: "p", agentId: "codex", cwd: "/p", title: "Bracket", status: "idle", archived: false } as unknown as Session;
const load = vi.fn(async () => undefined);
const close = vi.fn(async () => undefined);

beforeEach(() => {
  load.mockClear();
  close.mockClear();
  useAcp.setState({ sessions: {}, loading: {}, load, close } as never);
});

async function openMenu() {
  const user = userEvent.setup();
  render(
    <TooltipProvider>
      <SessionHeader session={SESSION} title="Bracket" />
    </TooltipProvider>,
  );
  await user.click(screen.getByRole("button", { name: "Session actions" }));
  return user;
}

describe("the session menu's agent item", () => {
  it("offers Disconnect agent while the agent is connected", async () => {
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "codex"), status: "idle" } } });
    await openMenu();
    expect(screen.getByRole("menuitem", { name: "Disconnect agent" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Reconnect" })).toBeNull();
  });

  it("offers Reconnect, not a second disconnect, once the agent is disconnected", async () => {
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "codex"), status: "closed" } } });
    const user = await openMenu();
    expect(screen.queryByRole("menuitem", { name: "Disconnect agent" })).toBeNull();
    await user.click(screen.getByRole("menuitem", { name: "Reconnect" }));
    expect(load).toHaveBeenCalledWith("s1");
    expect(close).not.toHaveBeenCalled();
  });
});

describe("the header's rename box", () => {
  it("a blur that follows Escape commits nothing", async () => {
    const rename = vi.fn(async () => undefined);
    useSessions.setState({ rename } as never);
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <SessionHeader session={SESSION} title="Bracket" />
      </TooltipProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Bracket" }));
    const input = screen.getByRole("textbox", { name: "Session title" });
    await user.clear(input);
    await user.type(input, "Renamed");
    // One act, so the box is still mounted when the blur lands, as when a browser blurs it on removal.
    act(() => {
      fireEvent.keyDown(input, { key: "Escape" });
      fireEvent.blur(input);
    });
    expect(rename).not.toHaveBeenCalled();
  });

  // Enter and Escape unmount the input that held focus; without a hand-off it fell to the page.
  it("hands focus back to the title button on Enter, and on Escape without saving", async () => {
    const rename = vi.fn(async () => undefined);
    useSessions.setState({ rename } as never);
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <SessionHeader session={SESSION} title="Bracket" />
      </TooltipProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Bracket" }));
    await user.keyboard("{Escape}");
    expect(rename).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Bracket" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Bracket" }));
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Bracket" })).toHaveFocus();
  });
});

describe("choosing Rename from the header menu", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("keeps the box and its draft after the menu's close focus has settled", async () => {
    const rename = vi.fn(async () => undefined);
    useSessions.setState({ rename } as never);
    const user = await openMenu();
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    // Whatever the menu does as it closes (trap, focus restore) must not end the edit by blurring the box.
    expect(screen.queryByRole("textbox", { name: "Session title" }), "the rename box stays open after the menu closes").toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Session title" }), { target: { value: "Not saved" } });
    // Past the menu's close, as the e2e's slow machine reaches it: any focus it moved off the box ends the edit.
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(rename, "rename must not run when the menu's close moves focus off the box").not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Session title" })).toHaveValue("Not saved");
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Session title" }), { key: "Escape" });
    expect(rename).not.toHaveBeenCalled();
  });
});

/**
 * One thread's row in the sidebar: its rename box and its actions button. The
 * sidebar's own suite draws whole panels; the details of a single row live here.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { SessionRow } from "@renderer/features/sidebar/SessionRow";
import { useSessions } from "@renderer/state/sessions";
import type { Session } from "@shared/types";

const SESSION = {
  id: "s1",
  projectId: "p1",
  title: "Bracket",
  titleSource: "prompt",
  agentId: "codex",
  cwd: "/repo",
  gitMode: "none",
  createdAt: 0,
  updatedAt: 0,
  status: "idle",
  acpSessionId: "acp",
  changedFiles: 0,
  insertions: 0,
  deletions: 0,
  archived: false,
  pinned: false,
  sessionHead: null,
  turnHead: null,
} as Session;

const rename = vi.fn(async () => undefined);

const row = () =>
  render(
    <TooltipProvider>
      <SessionRow onSelect={() => {}} selected={false} session={SESSION} showBranch={false} />
    </TooltipProvider>,
  );

const editBox = () => {
  fireEvent.doubleClick(screen.getByRole("button", { name: "Bracket" }));
  const input = screen.getByRole("textbox", { name: "Session title" });
  fireEvent.change(input, { target: { value: "Renamed" } });
  return input;
};

beforeEach(() => {
  rename.mockClear();
  useSessions.setState({ rename } as never);
});

describe("the rename box", () => {
  // Removing the focused input may blur it in some browsers, and `onBlur` commits the draft; jsdom
  // never blurs on removal, so these fire the blur themselves. Enter and Escape settle the edit
  // first (`settled`), and the blur that follows does nothing.
  it("Escape drops the edit", () => {
    row();
    const input = editBox();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(rename).not.toHaveBeenCalled();
  });

  it("a blur that follows Escape commits nothing (some browsers blur an input as it unmounts)", () => {
    row();
    const input = editBox();
    // One act, so the box is still mounted when the blur lands, as when a browser blurs it on removal.
    act(() => {
      fireEvent.keyDown(input, { key: "Escape" });
      fireEvent.blur(input);
    });
    expect(rename).not.toHaveBeenCalled();
  });

  it("a blur that follows Enter does not rename a second time", () => {
    row();
    const input = editBox();
    act(() => {
      fireEvent.keyDown(input, { key: "Enter" });
      fireEvent.blur(input);
    });
    expect(rename).toHaveBeenCalledTimes(1);
  });

  it("Enter renames once", () => {
    row();
    const input = editBox();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(rename).toHaveBeenCalledTimes(1);
    expect(rename).toHaveBeenCalledWith("s1", "Renamed");
  });
});

describe("after the rename box closes", () => {
  // Enter and Escape unmount the input that held focus; without a hand-off it fell to the page.
  it("Enter puts focus on the title button", () => {
    row();
    const input = editBox();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Bracket" }));
  });

  it("Escape leaves the title as it was and puts focus on the title button", () => {
    row();
    const input = editBox();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(rename).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Bracket" }));
  });
});

describe("the actions button", () => {
  it("shows itself when the keyboard reaches it, not only on hover", () => {
    row();
    // jsdom has no :focus-visible to evaluate, so the class is the only signal there is to check.
    expect(screen.getByRole("button", { name: "Bracket actions" })).toHaveClass("focus-visible:opacity-100");
  });
});

describe("the row's state", () => {
  // The glyph precedes the title button and is not a tab stop, so a screen-reader user landing on the
  // row heard only "Bracket". The word now rides on the button as its description.
  it("is the title button's accessible description when the agent needs you", () => {
    render(
      <TooltipProvider>
        <SessionRow onSelect={() => {}} selected={false} session={{ ...SESSION, status: "waiting" }} showBranch={false} />
      </TooltipProvider>,
    );
    expect(screen.getByRole("button", { name: "Bracket" })).toHaveAccessibleDescription(/Needs you|Waiting/);
  });
});

describe("choosing Rename from the actions menu", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  // Radix's menu pulls focus into itself while trapped and hands it to the `…` trigger a tick after
  // close; a box opened in the same breath as the choice lost focus, and its blur committed the draft.
  it("keeps the box and its draft after the menu's close focus has settled, and Escape still drops it", async () => {
    const user = userEvent.setup();
    row();
    const trigger = screen.getByRole("button", { name: "Bracket actions" });
    await user.click(trigger);
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
    expect(screen.getByRole("button", { name: "Bracket" })).toBeInTheDocument();
  });
});

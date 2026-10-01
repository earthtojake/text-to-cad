/**
 * One thread's row in the sidebar: its rename box and its actions button. The
 * sidebar's own suite draws whole panels; the details of a single row live here.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  // Pinned, not fixed: the worry was that removing the focused input blurs it and `onBlur`
  // commits the draft. Measured in Chromium with React 19, no blur reaches React on removal, so
  // Escape and Enter already end the edit once (jsdom does not blur on removal either).
  it("Escape drops the edit", () => {
    row();
    const input = editBox();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(rename).not.toHaveBeenCalled();
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

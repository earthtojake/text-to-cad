import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContextMeter } from "@renderer/features/session/ContextMeter";
import { EffortChip, ModeChip, ProjectChip } from "@renderer/features/session/ComposerChips";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { SelectOption } from "@shared/acp/options";
import type { Project, Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const BRACKET: Project = { id: "p1", name: "Gripper bracket", path: "/bracket", createdAt: 0 };
const GEARBOX: Project = { id: "p2", name: "Gearbox", path: "/gearbox", createdAt: 0 };

beforeEach(() => {
  useProjects.setState({ projects: [BRACKET, GEARBOX], activeId: BRACKET.id });
  useSessions.setState({ sessions: [] });
});

describe("the project chip's menu", () => {
  it("lists the folder it is in, checked, before any session has run there", async () => {
    render(<ProjectChip onChange={vi.fn()} project={BRACKET} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Gripper bracket" }));
    expect(screen.getByText("Recent")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Gripper bracket" })).toBeInTheDocument();
    // A folder with no live session is not recent; only the one the draft is in is listed.
    expect(screen.queryByRole("menuitem", { name: "Gearbox" })).toBeNull();
  });

  it("has no Recent heading with nothing under it", async () => {
    render(<ProjectChip onChange={vi.fn()} project={null} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Choose folder" }));
    expect(screen.getByRole("menuitem", { name: "Open folder…" })).toBeInTheDocument();
    expect(screen.queryByText("Recent")).toBeNull();
  });

  it("lists the folder once when a session has run there", async () => {
    useSessions.setState({ sessions: [{ id: "s1", projectId: BRACKET.id, archived: false, updatedAt: 1 } as unknown as Session] });
    render(<ProjectChip onChange={vi.fn()} project={BRACKET} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Gripper bracket" }));
    expect(screen.getAllByRole("menuitem", { name: "Gripper bracket" })).toHaveLength(1);
  });
});

describe("a chip's hint", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  /** Hover, let the kit's delay pass, and read which side Radix placed the hint on. */
  async function hintSide(chip: HTMLElement) {
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).hover(chip);
    act(() => vi.advanceTimersByTime(500));
    return (await screen.findByRole("tooltip")).closest("[data-side]")?.getAttribute("data-side");
  }

  it("opens below a chip in the row under the box, off the send button above it", async () => {
    render(<ModeChip currentModeId="ask" modes={[{ id: "ask", name: "Ask", description: "Asks first", kind: null }]} onChange={vi.fn()} />);
    expect(await hintSide(screen.getByRole("button", { name: "Ask" }))).toBe("bottom");
  });

  it("opens to the left of the row's right end — the effort chip, the context ring — which sits under send", async () => {
    // Below has no room in a live session (the row is 16px off the window's edge), and Radix flips a
    // bottom hint to the top: onto send.
    const effort: SelectOption = { id: "effort", name: "Effort", description: null, category: null, type: "select", currentValue: "medium", options: [{ value: "medium", name: "Medium", description: null, group: null, kind: null }] };
    render(<EffortChip effort={effort} onChange={vi.fn()} />);
    expect(await hintSide(screen.getByRole("button", { name: "Medium" }))).toBe("left");
    cleanup();
    render(<ContextMeter lastTurnUsage={null} rateLimits={{}} sessionId="s1" sessionUsage={null} usage={{ used: 50_000, size: 200_000, cost: null, breakdown: null }} />);
    expect(await hintSide(screen.getByRole("button", { name: "Context 25% used" }))).toBe("left");
  });

  it("opens above a chip in the strip over the box, off the sentence", async () => {
    render(<ProjectChip onChange={vi.fn()} project={BRACKET} />);
    expect(await hintSide(screen.getByRole("button", { name: "Gripper bracket" }))).toBe("top");
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ContextMeter } from "@renderer/features/session/ContextMeter";

/**
 * The context ring is a keyboard control like any other: it shows where focus is, and Enter on
 * it puts focus in the panel it opened — the panel is in a portal Tab from the ring cannot reach.
 */
function meter() {
  return render(
    <ContextMeter lastTurnUsage={null} rateLimits={{}} sessionId="s1" sessionUsage={null} usage={{ used: 50_000, size: 200_000, cost: null, breakdown: null }} />,
  );
}

describe("the context meter's keyboard behaviour", () => {
  it("draws a focus ring on the trigger", () => {
    meter();
    expect(screen.getByRole("button", { name: "Context 25% used" }).className).toContain("focus-visible:ring");
  });

  it("opens on Enter with focus inside the panel, and Escape gives it back to the ring", async () => {
    const user = userEvent.setup();
    meter();
    const trigger = screen.getByRole("button", { name: "Context 25% used" });
    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard("{Enter}");
    const panel = await screen.findByRole("dialog");
    expect(panel).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });
});

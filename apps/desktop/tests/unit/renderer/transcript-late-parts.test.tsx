import { render } from "@testing-library/react";
import { expect, it } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { Transcript } from "@renderer/features/session/Transcript";
import { initialSessionState, type SessionState } from "@shared/acp/types";

it("draws what arrived after the turn ended below Stopped, under a quiet label", () => {
  const state: SessionState = {
    ...initialSessionState("s1", "codex"),
    status: "idle",
    turns: [{
      id: "t1", role: "agent", startedAt: 1, endedAt: 2, stopReason: "cancelled", lateFrom: 1,
      parts: [{ type: "text", text: "Working on it." }, { type: "text", text: "Background task finished." }],
    }],
  };
  const { container } = render(
    <TooltipProvider><Transcript onReconnect={() => {}} onRetry={() => {}} state={state} /></TooltipProvider>,
  );
  const order = Array.from(container.querySelectorAll("[data-part='text'], [data-stopped], [data-late-label]")).map((node) => node.textContent?.trim());
  expect(order).toEqual(["Working on it.", "Stopped", "Arrived after the turn ended", "Background task finished."]);
});

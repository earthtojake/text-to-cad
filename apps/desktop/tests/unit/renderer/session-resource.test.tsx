import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { lastUserPrompt } from "@renderer/features/session/SessionView";
import { Transcript } from "@renderer/features/session/Transcript";
import { reduce } from "@shared/acp/reduce";
import { initialSessionState, type PromptBlock, type SessionState } from "@shared/acp/types";

const at = 1_000;
const attached: PromptBlock = { type: "resource", uri: "attachment:///notes%20v2.md", text: "# notes", mimeType: "text/markdown" };

function connected(): SessionState {
  return reduce(initialSessionState("s1", "fake"), {
    type: "session/connected",
    acpSessionId: "root",
    modes: null,
    configOptions: null,
    loading: false,
    at,
  });
}

function show(state: SessionState) {
  render(
    <TooltipProvider>
      <Transcript onReconnect={() => {}} onRetry={() => {}} state={state} />
    </TooltipProvider>,
  );
}

describe("an attached text file", () => {
  it("goes out again on Retry with its text, not as a link the agent cannot open", () => {
    const sent: PromptBlock[] = [{ type: "text", text: "see" }, attached];
    const state = reduce(connected(), { type: "prompt/start", turnId: "t1", content: sent, at });
    expect(lastUserPrompt(state)).toEqual(sent);
  });

  it("replays as an attachment chip, not as text glued onto the prompt", () => {
    let state = connected();
    for (const content of [
      { type: "text", text: "see" },
      { type: "resource", resource: { uri: attached.uri, text: "# notes", mimeType: "text/markdown" } },
    ]) {
      state = reduce(state, {
        type: "session/update",
        acpSessionId: "root",
        update: { sessionUpdate: "user_message_chunk", messageId: "m1", content },
        at,
      });
    }
    state = reduce(state, { type: "session/loaded", at });
    show(state);
    const turn = document.querySelector('[data-role="user"]');
    expect(turn?.textContent).not.toContain("# notes");
    expect(screen.getByText("see")).toBeInTheDocument();
    expect(screen.getByText("notes v2.md")).toBeInTheDocument();
  });
});

describe("a call its turn cancelled", () => {
  it("stops spinning and says it was cancelled", () => {
    let state = reduce(connected(), { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "go" }], at });
    state = reduce(state, {
      type: "session/update",
      acpSessionId: "root",
      update: { sessionUpdate: "tool_call", toolCallId: "c1", title: "sleep 100", kind: "execute", status: "in_progress" },
      at,
    });
    state = reduce(state, { type: "prompt/end", stopReason: "cancelled", usage: null, at });
    show(state);
    const row = document.querySelector('[data-activity-row="c1"]');
    expect(row?.getAttribute("data-status")).toBe("cancelled");
    expect(row?.querySelector(".animate-spin")).toBeNull();
    expect(row?.querySelector("[data-activity-cancelled]")?.textContent).toBe("Cancelled");
  });
});

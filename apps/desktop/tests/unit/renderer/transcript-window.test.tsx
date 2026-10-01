import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { Transcript, TRANSCRIPT_WINDOW } from "@renderer/features/session/Transcript";
import { initialSessionState, type SessionState, type ToolCallPart, type Turn } from "@shared/acp/types";

// A turn's body is not what is measured here, only which turns are in the
// document: switching back to a long session paid for mounting every one.
vi.mock("@renderer/features/session/parts/PartsList", () => ({
  PartsList: () => null,
}));

const agent = (id: string, parts: Turn["parts"] = [{ type: "text", text: id }]): Turn => ({
  id,
  role: "agent",
  parts,
  startedAt: 1,
  endedAt: 2,
  stopReason: "end_turn",
});
const turns = (count: number) => Array.from({ length: count }, (_, index) => agent(`t${index}`));
const session = (list: Turn[]): SessionState => ({ ...initialSessionState("s1", "codex"), status: "idle", turns: list });
const view = (state: SessionState) => (
  <TooltipProvider>
    <Transcript onReconnect={() => {}} onRetry={() => {}} state={state} />
  </TooltipProvider>
);
const mounted = () => Array.from(document.querySelectorAll("[data-turn]"), (node) => node.getAttribute("data-turn"));

// jsdom has no IntersectionObserver; this one is driven by hand. Like the
// real one it reports once when it starts observing, with the sentinel where
// the test last put it — jsdom lays nothing out, so it never moves by itself.
let visible = false;
let intersect: (now: boolean) => void = () => {};
class FakeIntersectionObserver {
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(target: Element) {
    const report = () =>
      this.callback([{ isIntersecting: visible, target } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
    intersect = (now) => {
      visible = now;
      report();
    };
    report();
  }
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
}

// A transcript taller than its pane, so the pane scrolls and "at the bottom"
// means something. jsdom computes no stylesheet, so the pane's `overflow` —
// which the library reads to find what a wheel scrolls — is set inline.
const tall = (element: HTMLElement) => {
  element.style.overflow = "auto";
  Object.defineProperty(element, "scrollHeight", { configurable: true, value: 4000 });
  Object.defineProperty(element, "clientHeight", { configurable: true, value: 600 });
};
const scroller = () => {
  let node = document.querySelector("[data-turn]")!.parentElement!;
  while (node.style.height !== "100%") node = node.parentElement!;
  return node;
};

beforeEach(() => {
  visible = false;
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a long transcript mounts its latest turns", () => {
  it("mounts only the last window of turns when it opens", () => {
    render(view(session(turns(40))));
    expect(mounted()).toEqual(turns(40).slice(-TRANSCRIPT_WINDOW).map((turn) => turn.id));
    expect(screen.getByRole("button", { name: `Show ${40 - TRANSCRIPT_WINDOW} earlier turns` })).toBeTruthy();
  });

  it("mounts every turn of a short transcript, with no sentinel", () => {
    render(view(session(turns(TRANSCRIPT_WINDOW))));
    expect(mounted()).toHaveLength(TRANSCRIPT_WINDOW);
    expect(document.querySelector("[data-earlier-turns]")).toBeNull();
  });

  it("mounts earlier turns once the person scrolls up to the sentinel", async () => {
    render(view(session(turns(40))));
    const pane = scroller();
    tall(pane);
    // Opening at the bottom, the sentinel may be inside its margin; nothing is mounted for that.
    act(() => intersect(true));
    expect(mounted()).toHaveLength(TRANSCRIPT_WINDOW);

    // A wheel up leaves the bottom, with the sentinel still in reach: the next window mounts.
    act(() => {
      fireEvent.wheel(pane, { deltaY: -120 });
    });
    expect(mounted()).toHaveLength(40);
    expect(mounted()[0]).toBe("t0");
  });

  it("does not mount a second window for a scroll the person did not make", async () => {
    render(view(session(turns(48))));
    const pane = scroller();
    tall(pane);
    // Opening, the pane's content settles and its offset is clamped down: a
    // scroll event moving up, which the library reads as an escape from the
    // bottom. No wheel, key or touch was behind it.
    for (const top of [500, 100]) {
      pane.scrollTop = top;
      fireEvent.scroll(pane);
      await act(() => new Promise((resolve) => setTimeout(resolve, 10)));
    }
    act(() => intersect(true));
    expect(mounted()).toHaveLength(TRANSCRIPT_WINDOW);
    expect(screen.getByRole("button", { name: `Show ${48 - TRANSCRIPT_WINDOW} earlier turns` })).toBeTruthy();
  });

  it("mounts a second window only for a press on the pane itself, its scrollbar", async () => {
    render(view(session(turns(48))));
    const pane = scroller();
    tall(pane);
    // Off the bottom, as the opening's clamp leaves it, with no reach behind it.
    for (const top of [500, 100]) {
      pane.scrollTop = top;
      fireEvent.scroll(pane);
      await act(() => new Promise((resolve) => setTimeout(resolve, 10)));
    }
    // A press on a turn is a click on the page, not a reach for what is above.
    act(() => {
      fireEvent.pointerDown(document.querySelector("[data-turn]")!);
    });
    act(() => intersect(true));
    expect(mounted()).toHaveLength(TRANSCRIPT_WINDOW);

    // A press on the pane itself is its scrollbar being dragged.
    act(() => {
      fireEvent.pointerDown(pane);
    });
    // The drag scrolls, and the sentinel comes into reach again on the way up.
    act(() => intersect(false));
    act(() => intersect(true));
    expect(mounted().length).toBeGreaterThan(TRANSCRIPT_WINDOW);
  });

  it("mounts the next window for a reach that lands with the sentinel already in reach, off the bottom", async () => {
    render(view(session(turns(48))));
    const pane = scroller();
    tall(pane);
    // Off the bottom with no reach behind it, the sentinel in reach: nothing mounts.
    for (const top of [500, 100]) {
      pane.scrollTop = top;
      fireEvent.scroll(pane);
    }
    await screen.findByRole("button", { name: "Jump to latest" });
    act(() => intersect(true));
    expect(mounted()).toHaveLength(TRANSCRIPT_WINDOW);

    // The wheel up is the reach, and nothing else changes: the window mounts for it.
    act(() => {
      fireEvent.wheel(pane, { deltaY: -120 });
    });
    expect(mounted().length).toBeGreaterThan(TRANSCRIPT_WINDOW);
  });

  it("keeps the turns an early permission request pulled in once it is answered", () => {
    const request = (state: "pending" | "cancelled"): Turn["parts"][number] => ({
      type: "permission_request",
      requestId: "r1",
      toolCallId: "c1",
      title: "Edit car.py",
      description: null,
      options: [],
      outcome: { state },
    });
    const list = turns(40);
    list[5] = agent("t5", [request("pending")]);
    const { rerender } = render(view(session(list)));
    expect(mounted()[0]).toBe("t5");
    const answered = [...list];
    answered[5] = agent("t5", [request("cancelled")]);
    rerender(view(session(answered)));
    expect(mounted()[0]).toBe("t5");
    expect(mounted()).toHaveLength(35);
  });

  it("mounts earlier turns inside a silent live region, and a new turn outside it", () => {
    const list = turns(2 * TRANSCRIPT_WINDOW);
    const { rerender } = render(view(session(list)));
    fireEvent.click(screen.getByRole("button", { name: `Show ${TRANSCRIPT_WINDOW} earlier turns` }));
    const silent = (id: string) => document.querySelector(`[data-turn="${id}"]`)!.closest('[aria-live="off"]');
    // The transcript is `role=log`, live by default: what the person scrolled up to is not news.
    expect(silent("t0")).not.toBeNull();
    expect(silent(`t${TRANSCRIPT_WINDOW - 1}`)).not.toBeNull();
    expect(silent(`t${2 * TRANSCRIPT_WINDOW - 1}`)).toBeNull();
    rerender(view(session([...list, agent("new")])));
    expect(silent("new")).toBeNull();
  });

  it("draws the silent live region as a box, not as display: contents", () => {
    render(view(session(turns(2 * TRANSCRIPT_WINDOW))));
    fireEvent.click(screen.getByRole("button", { name: `Show ${TRANSCRIPT_WINDOW} earlier turns` }));
    // `display: contents` has left Chromium's accessibility tree, and `aria-live` with it.
    const region = document.querySelector<HTMLElement>('[data-earlier-region][aria-live="off"]')!;
    expect(region.className.split(" ")).not.toContain("contents");
    // Wraps the turns mounted on demand, and not the window the transcript opened with.
    expect(region.querySelectorAll("[data-turn]")).toHaveLength(TRANSCRIPT_WINDOW);
  });

  it("collapses the on-demand region when nothing is in it, so the column's gap is not spent on it", () => {
    render(view(session(turns(5))));
    const region = document.querySelector<HTMLElement>("[data-earlier-region]")!;
    // jsdom applies no stylesheet: the region is empty, and says what an empty one does.
    expect(region.childElementCount).toBe(0);
    expect(region.className.split(" ")).toContain("empty:hidden");
  });

  it("mounts the next window from the sentinel's button", () => {
    render(view(session(turns(40))));
    fireEvent.click(screen.getByRole("button", { name: `Show ${40 - TRANSCRIPT_WINDOW} earlier turns` }));
    expect(mounted()).toHaveLength(2 * TRANSCRIPT_WINDOW);
    fireEvent.click(screen.getByRole("button", { name: `Show ${40 - 2 * TRANSCRIPT_WINDOW} earlier turns` }));
    expect(mounted()).toHaveLength(3 * TRANSCRIPT_WINDOW);
  });

  it("keeps the new turn mounted and drops none when one arrives", () => {
    const list = turns(40);
    const { rerender } = render(view(session(list)));
    rerender(view(session([...list, agent("t40")])));
    expect(mounted().at(-1)).toBe("t40");
    expect(mounted()[0]).toBe(`t${40 - TRANSCRIPT_WINDOW}`);
    expect(mounted()).toHaveLength(TRANSCRIPT_WINDOW + 1);
  });

  it("mounts an earlier turn that holds an unanswered permission request", () => {
    const pending = (outcome: { state: "pending" } | { state: "cancelled" }): Turn["parts"][number] => ({
      type: "permission_request",
      requestId: "r1",
      toolCallId: "c1",
      title: "Edit car.py",
      description: null,
      options: [],
      outcome,
    });
    const list = turns(40);
    list[5] = agent("t5", [pending({ state: "pending" })]);
    list[3] = agent("t3", [pending({ state: "cancelled" })]);
    render(view(session(list)));
    expect(mounted()[0]).toBe("t5");
    expect(mounted()).toHaveLength(35);
  });

  it("finds an unanswered request inside a tool call's children", () => {
    const child: Turn["parts"][number] = {
      type: "permission_request",
      requestId: "r1",
      toolCallId: "c1",
      title: null,
      description: null,
      options: [],
      outcome: { state: "pending" },
    };
    const task: ToolCallPart = {
      type: "tool_call",
      id: "task",
      kind: "think",
      title: "Task",
      name: null,
      status: "in_progress",
      input: undefined,
      output: undefined,
      content: [],
      locations: [],
      stream: "",
      children: [child],
    };
    const list = turns(40);
    list[10] = agent("t10", [task]);
    render(view(session(list)));
    expect(mounted()[0]).toBe("t10");
  });
});

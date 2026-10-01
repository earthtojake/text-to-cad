import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { initialSessionState, type LiveStatus } from "@shared/acp/types";
import type { Session } from "@shared/types";

/**
 * The composer's model and mode chips and its Stop call main, which refuses a session with no
 * live agent (`requireLive`). Those refusals reach the person as a toast, and the chips are not
 * offered at all unless the agent is there to answer them.
 */

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));
vi.mock("@renderer/features/session/Composer", () => ({
  Composer: ({ chips, trailing, onStop }: { chips: React.ReactNode; trailing: React.ReactNode; onStop: () => void }) => (
    <div>
      {chips}
      {trailing}
      <button onClick={onStop} type="button">Stop</button>
    </div>
  ),
}));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/Transcript", () => ({ Transcript: () => null }));
vi.mock("@renderer/features/session/ContextMeter", () => ({ ContextMeter: () => null }));

const SESSION = { id: "s1", projectId: "p1", agentId: "codex", cwd: "/p", title: "t", status: "idle" } as unknown as Session;
const refused = () => Promise.reject(new Error("the session is not connected; load it first"));
const setMode = vi.fn(refused);
const setConfigOption = vi.fn(refused);
const cancel = vi.fn(refused);

function state(status: LiveStatus) {
  return {
    ...initialSessionState("s1", "codex"),
    status,
    currentModeId: "ask",
    modes: [{ id: "ask", name: "Ask", description: null }, { id: "plan", name: "Plan", description: null }],
    configOptions: [{ id: "model", name: "Model", type: "select", category: "model", currentValue: "a", options: [{ value: "a", name: "Model A" }, { value: "gpt", name: "GPT" }] }],
  } as never;
}

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.info).mockClear();
  setMode.mockClear();
  setConfigOption.mockClear();
  cancel.mockClear();
  useAcp.setState({ sessions: {}, loading: {}, reconnecting: {}, loadErrors: {}, ensureLoaded: vi.fn(async () => undefined), setMode, setConfigOption, cancel } as never);
});

/** The real chips: the mode chip is labelled with the current mode, the model chip with the model. */
const CHIPS = { Mode: "Ask", Model: "Model A" } as const;
const chipNamed = (chip: keyof typeof CHIPS) => screen.getByRole("button", { name: CHIPS[chip] });
/** Open a chip's menu and pick an item, as a person does. */
async function choose(chip: keyof typeof CHIPS, item: string) {
  const user = userEvent.setup();
  await user.click(chipNamed(chip));
  await user.click(await screen.findByRole("menuitemradio", { name: item }));
}

describe("the composer's chips and Stop", () => {
  it("tell the person why main refused, rather than failing unhandled", async () => {
    useAcp.setState({ sessions: { s1: state("running") } } as never);
    render(<SessionView session={SESSION} />);
    await choose("Mode", "Plan");
    await choose("Model", "GPT");
    await act(async () => screen.getByRole("button", { name: "Stop" }).click());
    expect(setMode).toHaveBeenCalled();
    expect(setConfigOption).toHaveBeenCalled();
    expect(cancel).toHaveBeenCalled();
    expect(vi.mocked(toast.error).mock.calls.map(([message]) => String(message))).toEqual([
      expect.stringMatching(/mode.*not connected/i),
      expect.stringMatching(/model.*not connected/i),
      expect.stringMatching(/stop.*not connected/i),
    ]);
  });

  it.each([
    ["closed", false, "Agent disconnected"],
    ["error", false, "Agent disconnected"],
    ["connecting", false, "Connecting…"],
    ["idle", true, "Reconnecting…"],
  ] as const)("stay in the tree on a %s session (reconnecting: %s), disabled, with the reason as their description", async (status, reconnecting, reason) => {
    useAcp.setState({ sessions: { s1: state(status) }, reconnecting: reconnecting ? { s1: true } : {} } as never);
    render(<SessionView session={SESSION} />);
    for (const name of ["Mode", "Model"] as const) {
      const chip = chipNamed(name);
      expect(chip, name).toHaveAttribute("aria-disabled", "true");
      expect(chip, name).toHaveAccessibleDescription(reason);
      expect(chip, name).not.toHaveAttribute("title");
      await userEvent.setup().click(chip);
      expect(screen.queryByRole("menu"), name).toBeNull();
    }
    expect(setMode).not.toHaveBeenCalled();
    expect(setConfigOption).not.toHaveBeenCalled();
    expect(vi.mocked(toast.info).mock.calls).toEqual([[reason], [reason]]);
  });

  it("say why from the keyboard too, where the refused activation has no click to say it", async () => {
    useAcp.setState({ sessions: { s1: state("closed") }, reconnecting: {} } as never);
    render(<SessionView session={SESSION} />);
    const chip = chipNamed("Mode");
    act(() => chip.focus());
    await userEvent.setup().keyboard("{Enter}");
    await userEvent.setup().keyboard(" ");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(vi.mocked(toast.info).mock.calls).toEqual([["Agent disconnected"], ["Agent disconnected"]]);
  });

  it("open a choice menu on the checked item, not the first", async () => {
    useAcp.setState({ sessions: { s1: { ...(state("idle") as object), currentModeId: "plan" } } } as never);
    render(<SessionView session={SESSION} />);
    act(() => screen.getByRole("button", { name: "Plan" }).focus());
    await userEvent.setup().keyboard("{Enter}");
    const checked = await screen.findByRole("menuitemradio", { name: "Plan" });
    expect(checked).toHaveAttribute("aria-checked", "true");
    expect(checked).toHaveFocus();
  });

  it("close an open menu when the agent goes away under it", async () => {
    useAcp.setState({ sessions: { s1: state("idle") }, reconnecting: {} } as never);
    render(<SessionView session={SESSION} />);
    await userEvent.setup().click(chipNamed("Mode"));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    act(() => useAcp.setState({ sessions: { s1: state("closed") } } as never));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("stay as they were, disabled, after Disconnect agent forgets the session's state", () => {
    useAcp.setState({ sessions: { s1: state("idle") } } as never);
    const { rerender } = render(<SessionView session={SESSION} />);
    // `close` in state/acp.ts forgets the state; the row says closed.
    act(() => useAcp.setState({ sessions: {} } as never));
    rerender(<SessionView session={{ ...SESSION, status: "closed" } as Session} />);
    for (const name of ["Mode", "Model"] as const) {
      expect(chipNamed(name), name).toHaveAttribute("aria-disabled", "true");
      expect(chipNamed(name), name).toHaveAccessibleDescription("Agent disconnected");
    }
  });

  it("are offered on an idle session", () => {
    useAcp.setState({ sessions: { s1: state("idle") } } as never);
    render(<SessionView session={SESSION} />);
    const chip = chipNamed("Mode");
    expect(chip).not.toHaveAttribute("aria-disabled");
    // Its hint is the kit's tooltip, not a native `title`, so nothing describes it at rest.
    expect(chip).not.toHaveAttribute("title");
    expect(chip).not.toHaveAccessibleDescription();
  });

  it("keep a keyboard user's focus when the agent comes back", () => {
    useAcp.setState({ sessions: { s1: state("idle") }, reconnecting: { s1: true } } as never);
    render(<SessionView session={SESSION} />);
    const chip = chipNamed("Mode");
    act(() => chip.focus());
    expect(chip).toHaveAttribute("aria-disabled", "true");
    act(() => useAcp.setState({ reconnecting: {} }));
    expect(chipNamed("Mode")).not.toHaveAttribute("aria-disabled");
    expect(chipNamed("Mode")).toHaveFocus();
  });
});

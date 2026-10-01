import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { expect, it, vi } from "vitest";
import { DesktopCadFailure } from "@renderer/features/explorer/adapters/cadRuntime";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

it("a runtime failure offers to reveal its log instead of printing the path", async () => {
  const user = userEvent.setup();
  const onReady = vi.fn();
  const log = "/Users/me/Library/Logs/text-to-cad/cad-runtime.log";
  render(<DesktopCadFailure answer={{ reason: "runtime-not-ready", message: "cadgen: not found", log } as never}
    onReady={onReady} reload={() => {}} />);
  expect(screen.queryByText(/^Log:/)).toBeNull();
  expect(screen.queryByText(log)).toBeNull();
  const reveal = vi.mocked(window.textToCad.runtime.revealLog);
  reveal.mockResolvedValueOnce({ revealed: true });
  await user.click(screen.getByRole("button", { name: "Reveal log" }));
  expect(reveal).toHaveBeenCalledTimes(1);
  expect(toast.error).not.toHaveBeenCalled();
  // The file is gone by the time it is asked for: say so.
  reveal.mockResolvedValueOnce({ revealed: false });
  await user.click(screen.getByRole("button", { name: "Reveal log" }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith("There is no runtime log yet."));
  expect(onReady).toHaveBeenCalledWith(false);
});

it("no log, no Reveal log button", () => {
  render(<DesktopCadFailure answer={{ reason: "runtime-not-ready", message: "cadgen: not found" } as never}
    onReady={() => {}} reload={() => {}} />);
  expect(screen.queryByRole("button", { name: "Reveal log" })).toBeNull();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

it("a file whose project is gone says how to get it back and can try again", async () => {
  const reload = vi.fn();
  render(<DesktopCadFailure answer={{ origin: null, reason: "no-project" } as never} onReady={() => {}} reload={reload} />);
  expect(screen.getByText("Select a session in this folder to render its files.")).toBeInTheDocument();
  screen.getByRole("button", { name: "Try again" }).click();
  expect(reload).toHaveBeenCalledTimes(1);
});

it("a failing override interpreter is named, not blamed on the runtime that ships with the app", async () => {
  vi.mocked(window.textToCad.runtime.status).mockResolvedValueOnce({ state: "error", python: "/nowhere/python", source: "override", cadgenVersion: null, viewerBuilt: false, log: null, message: "no interpreter at /nowhere/python" });
  render(<DesktopCadFailure answer={{ origin: null, reason: "runtime-not-ready", message: "The override interpreter (/nowhere/python) cannot import cadgen" } as never}
    onReady={() => {}} reload={() => {}} />);
  expect(await screen.findByText(/override interpreter at \/nowhere\/python could not run cadgen/)).toBeInTheDocument();
  expect(screen.getByText(/CAD_DESKTOP_PYTHON or the cadPythonOverride setting/)).toBeInTheDocument();
  expect(screen.queryByText(/ships with text-to-cad could not run cadgen/)).toBeNull();
});

it("Try again on a runtime card forgets the failed probe before it reloads", async () => {
  const reload = vi.fn();
  vi.mocked(window.textToCad.runtime.repair).mockResolvedValueOnce({ state: "ready", python: "/py", source: "bundled", cadgenVersion: "1", viewerBuilt: true, log: null, message: null } as never);
  render(<DesktopCadFailure answer={{ origin: null, reason: "runtime-not-ready", message: "cadgen: not found" } as never} onReady={() => {}} reload={reload} />);
  await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  expect(window.textToCad.runtime.repair).toHaveBeenCalledTimes(1);
  expect(vi.mocked(window.textToCad.runtime.repair).mock.invocationCallOrder[0]).toBeLessThan(reload.mock.invocationCallOrder[0]!);
});

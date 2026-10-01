import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { AboutPage } from "@renderer/features/settings/pages/AboutPage";
import { useSettings } from "@renderer/state/settings";
import { useUpdates } from "@renderer/state/updates";
import { defaultSettings } from "@shared/types";

/** Settings › About › Software update: the one row the updater's state draws. */
type AppApi = Record<string, unknown>;
const app = () => window.textToCad.app as unknown as AppApi;

beforeEach(() => {
  useSettings.setState({ settings: defaultSettings(), ready: true });
  useUpdates.setState({ status: { state: "downloaded", version: "2.0.0" }, busy: false });
});

afterEach(() => {
  delete app().installUpdate;
  delete app().checkForUpdates;
});

function renderAbout() {
  return render(<TooltipProvider><AboutPage /></TooltipProvider>);
}

describe("About › Software update", () => {
  it("Restart goes disabled on the first press, so a second press never reaches main", async () => {
    const installUpdate = vi.fn(() => new Promise<void>(() => undefined));
    app().installUpdate = installUpdate;
    renderAbout();
    const restart = screen.getByRole("button", { name: /Restart/ });
    await userEvent.click(restart);
    await waitFor(() => expect(restart).toBeDisabled());
    await userEvent.click(restart);
    expect(installUpdate).toHaveBeenCalledTimes(1);
    expect(restart).toHaveTextContent("Restarting…");
  });

  it("Restart stays disabled and reads Restarting… after main has answered, until the quit or an error", async () => {
    app().installUpdate = vi.fn(async () => undefined);
    renderAbout();
    await userEvent.click(screen.getByRole("button", { name: /Restart/ }));
    const restarting = await screen.findByRole("button", { name: "Restarting…" });
    expect(restarting).toBeDisabled();
    expect(useUpdates.getState().busy).toBe(false);

    // main gave up on it: the row is an error again, with Restart to retry.
    act(() => {
      useUpdates.getState().receive({ state: "error", message: "The update did not start; try Restart again.", version: "2.0.0" });
    });
    expect(screen.getByRole("button", { name: /Restart/ })).toBeEnabled();
  });

  it("a failing install lands as an error status instead of an unhandled rejection", async () => {
    app().installUpdate = vi.fn(async () => {
      throw new Error("ipc went away");
    });
    renderAbout();
    await userEvent.click(screen.getByRole("button", { name: /Restart/ }));
    expect(await screen.findByText("ipc went away")).toBeInTheDocument();
    expect(useUpdates.getState().busy).toBe(false);
  });

  it("clamps a long error to a line's worth", () => {
    useUpdates.setState({ status: { state: "error", message: "e".repeat(500) } });
    renderAbout();
    const text = screen.getByText(/^e+…$/).textContent ?? "";
    expect(text.length).toBeLessThanOrEqual(160);
  });

  it("announces the state in a live region", () => {
    useUpdates.setState({ status: { state: "available", version: "2.0.0" } });
    renderAbout();
    expect(screen.getByRole("status")).toHaveTextContent("Version 2.0.0 is available");
  });

  it("exposes the download as a named progress bar", () => {
    useUpdates.setState({ status: { state: "downloading", version: "2.0.0", percent: 40 } });
    renderAbout();
    // The live region is not rewritten by every progress event.
    expect(screen.getByRole("status")).toHaveTextContent("Downloading 2.0.0…");
    expect(screen.getByRole("status").textContent).not.toMatch(/\d+%/);
    expect(screen.getByText("40%")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: /download/i });
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("names Restart for the version it installs", () => {
    renderAbout();
    expect(screen.getByRole("button", { name: /Restart.*2\.0\.0/ })).toBeInTheDocument();
  });

  it("a check that finds nothing says the build is up to date", async () => {
    app().checkForUpdates = vi.fn(async () => ({ state: "idle" as const }));
    useUpdates.setState({ status: { state: "idle" } });
    renderAbout();
    await userEvent.click(screen.getByRole("button", { name: "Check now" }));
    await waitFor(() => expect(app().checkForUpdates).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent("text-to-cad is up to date.");
  });

  it("an install the updater is inactive for does not claim to run from a checkout", () => {
    useUpdates.setState({ status: { state: "unsupported", message: "This install has no update channel, so updates are not available." } });
    renderAbout();
    expect(screen.getByRole("status")).toHaveTextContent("This install has no update channel");
    expect(screen.getByRole("status")).not.toHaveTextContent(/checkout/i);
  });
});

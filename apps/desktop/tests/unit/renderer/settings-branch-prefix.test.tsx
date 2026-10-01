/**
 * The branch prefix row says what became of a prefix git refuses: one stored
 * before the check existed (main reads it as the default), and one typed and
 * then left behind when Settings closes.
 */
import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { GitPage } from "@renderer/features/settings/pages/GitPage";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  useSettings.setState({ settings: defaultSettings(), ready: true });
});

it("notes a stored prefix main refused and read as the default", async () => {
  vi.mocked(window.textToCad.settings.fallbacks).mockResolvedValue({ refused: { branchPrefix: "a b/" }, gone: {} });
  wrap(<GitPage />);
  expect(await screen.findByText(/The stored prefix “a b\/” is not one git accepts/)).toHaveTextContent(
    "Git refuses spaces in a branch name.",
  );
});

it("draws the stored prefix's note in the kit's warning tone, not as a muted description", async () => {
  vi.mocked(window.textToCad.settings.fallbacks).mockResolvedValue({ refused: { branchPrefix: "feature..x/" }, gone: {} });
  wrap(<GitPage />);
  const note = await screen.findByText(/The stored prefix “feature\.\.x\/” is not one git accepts/);
  expect(note).not.toHaveClass("text-muted-foreground");
  // The kit's Alert, warning variant: its amber border and wash.
  expect(note.closest("[data-slot=alert]")).toHaveClass("bg-chart-5/10");
});

it("stores the default over a bad stored prefix from Use default, which retyping it cannot", async () => {
  const user = userEvent.setup();
  vi.mocked(window.textToCad.settings.fallbacks).mockResolvedValueOnce({ refused: { branchPrefix: "feature..x/" }, gone: {} }).mockResolvedValue({ refused: {}, gone: {} });
  vi.mocked(window.textToCad.settings.set).mockImplementation(async (patch) => ({ ...defaultSettings(), ...(patch as object) }));
  wrap(<GitPage />);
  await screen.findByText(/The stored prefix “feature\.\.x\/”/);

  await user.click(screen.getByRole("button", { name: "Use default" }));

  expect(window.textToCad.settings.set).toHaveBeenCalledWith({ branchPrefix: defaultSettings().branchPrefix });
  await waitFor(() => expect(screen.queryByText(/The stored prefix/)).toBeNull());
});

it("says a refused prefix was not saved when Settings closes on it", async () => {
  vi.mocked(window.textToCad.settings.fallbacks).mockResolvedValue({ refused: {}, gone: {} });
  const user = userEvent.setup();
  const page = wrap(<GitPage />);
  const box = screen.getByRole("textbox", { name: "Branch prefix" });
  await user.clear(box);
  await user.type(box, "a..b/");
  page.unmount();
  expect(window.textToCad.settings.set).not.toHaveBeenCalled();
  expect(toast.error).toHaveBeenCalledWith("Branch prefix “a..b/” was not saved", {
    description: "Git refuses “..” in a branch name.",
  });
});

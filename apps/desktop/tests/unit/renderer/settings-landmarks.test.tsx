import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings } from "@shared/types";

/** Settings is a page: a main, a named nav, one h1, and a search that says how many rows it found. */
beforeEach(() => {
  useUi.setState({ route: "settings", settingsSection: "general", commandPaletteOpen: false });
  useSettings.setState({ settings: defaultSettings(), ready: true });
});

const open = () => render(<TooltipProvider><SettingsRoute /></TooltipProvider>);

it("has a main and a navigation named Settings", () => {
  open();
  expect(screen.getByRole("main")).toContainElement(screen.getByRole("heading", { level: 1, name: "General" }));
  expect(within(screen.getByRole("navigation", { name: "Settings" })).getByRole("button", { name: "General" })).toHaveAttribute("aria-current", "page");
});

it("keeps one h1 while searching, with each page's heading under it, and counts the matching rows", async () => {
  const user = userEvent.setup();
  open();
  await user.type(screen.getByRole("textbox", { name: "Search settings" }), "branch prefix");
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 2, name: "Git and worktrees" })).toBeInTheDocument();
  expect(await screen.findByRole("status")).toHaveTextContent(/^1 row matches$/);
});

it("counts rows, not the cards that hold them", async () => {
  const user = userEvent.setup();
  open();
  // "sound" matches three rows on the General page, all in one card.
  await user.type(screen.getByRole("textbox", { name: "Search settings" }), "sound");
  expect(await screen.findByRole("status")).toHaveTextContent(/^3 rows match$/);
});

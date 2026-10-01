/**
 * The welcome is one of the window's three routes, and Settings replaces it
 * the way it replaces the shell: what the welcome remembers has to live in a
 * store, or a trip to Settings › Agents from the agent step comes back to the
 * first step.
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { App } from "@renderer/app/App";
import { useAgents } from "@renderer/state/agents";
import { useOnboarding } from "@renderer/state/onboarding";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings } from "@shared/types";

vi.mock("@renderer/app/Shell", () => ({ Shell: () => null }));
vi.mock("@renderer/app/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@renderer/features/settings/SettingsRoute", () => ({ SettingsRoute: () => <p>Settings</p> }));
vi.mock("@renderer/state/bridge", () => ({ hydrate: vi.fn(async () => undefined), subscribeToMain: () => () => undefined }));

it("comes back to the agent step, not the first, after a trip to Settings", async () => {
  useOnboarding.setState({ enabled: true });
  useSettings.setState({ settings: { ...defaultSettings(), onboardingCompleted: false }, ready: true });
  useAgents.setState({ agents: [], ready: true, loadError: null, jobs: {} });
  useUi.setState({ route: "app" });
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: /Continue/ }));
  expect(screen.getByRole("heading", { name: "Connect an agent" })).toBeInTheDocument();

  act(() => useUi.getState().openSettings("agents"));
  expect(screen.getByText("Settings")).toBeInTheDocument();
  act(() => useUi.getState().closeSettings());
  expect(screen.getByRole("heading", { name: "Connect an agent" })).toBeInTheDocument();
});

/**
 * `onboarding.createSample` copies the sample and makes it a folder main
 * chose, but does not select it in the window: the welcome that asked
 * selects it, and only if the person is still there (Back cancels it).
 */
import { expect, it, vi } from "vitest";

const sample = { id: "/docs/sample", name: "text-to-cad Sample", path: "/docs/sample", createdAt: 0 };
const choose = vi.hoisted(() => vi.fn());
const broadcast = vi.hoisted(() => vi.fn());
vi.mock("@main/db/repositories", () => ({ projects: { choose } }));
vi.mock("@main/ipc/register", () => ({ IpcError: class extends Error {}, broadcast }));
vi.mock("@main/onboarding", () => ({ createSampleProject: () => "/docs/sample", onboardingEnabled: () => true }));

import { onboardingHandlers } from "@main/ipc/onboarding";

it("answers with the sample main chose, and broadcasts no selection", () => {
  choose.mockReturnValue(sample);
  expect(onboardingHandlers.onboarding.createSample()).toEqual(sample);
  expect(choose).toHaveBeenCalledWith("/docs/sample");
  expect(broadcast).not.toHaveBeenCalled();
});

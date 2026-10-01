/**
 * The e2e suite chooses folders through a door on main's global
 * (`chooseDirectory` in tests/e2e/launch.ts). It is there only for a test
 * launch of a development build: `NODE_ENV=test` is an environment variable,
 * and anyone can set one in front of a packaged app.
 */
import { afterEach, expect, it, vi } from "vitest";

const choose = vi.hoisted(() => vi.fn((directory: string) => ({ id: directory, name: "p", path: directory, createdAt: 0 })));
const broadcast = vi.hoisted(() => vi.fn());
vi.mock("electron", () => ({ app: { isPackaged: false } }));
vi.mock("@main/db/repositories", () => ({ projects: { choose } }));
vi.mock("@main/ipc/register", () => ({ broadcast }));

import { installE2eDoor } from "@main/test-door";

const door = () => (globalThis as { __textToCadE2E?: { choose(directory: string): unknown } }).__textToCadE2E;

afterEach(() => {
  delete (globalThis as { __textToCadE2E?: unknown }).__textToCadE2E;
});

it("is installed for a test launch of a development build, and chooses as the chooser does", () => {
  installE2eDoor({ NODE_ENV: "test" }, false);
  expect(door()?.choose("/work")).toMatchObject({ path: "/work" });
  expect(broadcast).toHaveBeenCalledWith("ui.directorySelected", expect.objectContaining({ path: "/work" }));
});

it("is not installed outside a test launch, nor in a packaged app launched as one", () => {
  installE2eDoor({ NODE_ENV: "production" }, false);
  expect(door()).toBeUndefined();
  installE2eDoor({ NODE_ENV: "test" }, true);
  expect(door()).toBeUndefined();
});

/**
 * The e2e suite chooses folders through a door on main's global
 * (`chooseDirectory` in tests/e2e/launch.ts). It is there only for a test
 * launch of a development build: `NODE_ENV=test` is an environment variable,
 * and anyone can set one in front of a packaged app.
 */
import { afterEach, expect, it, vi } from "vitest";

// A connection is busy while one of its statements is stepping — and better-sqlite3 builds each
// row by calling into JS, so JS can run inside that window. `inStatement` is that window.
const sqlite = vi.hoisted(() => ({ inStatement: false }));
const choose = vi.hoisted(() =>
  vi.fn((directory: string) => {
    if (sqlite.inStatement) throw new TypeError("This database connection is busy executing a query");
    return { id: directory, name: "p", path: directory, createdAt: 0 };
  }),
);
const broadcast = vi.hoisted(() => vi.fn());
vi.mock("electron", () => ({ app: { isPackaged: false } }));
vi.mock("@main/db/repositories", () => ({ projects: { choose } }));
vi.mock("@main/ipc/register", () => ({ broadcast }));

import { installE2eDoor } from "@main/test-door";

const door = () => (globalThis as { __textToCadE2E?: { choose(directory: string): Promise<unknown> } }).__textToCadE2E;

afterEach(() => {
  delete (globalThis as { __textToCadE2E?: unknown }).__textToCadE2E;
  sqlite.inStatement = false;
  choose.mockClear();
  broadcast.mockClear();
});

it("is installed for a test launch of a development build, and chooses as the chooser does", async () => {
  installE2eDoor({ NODE_ENV: "test" }, false);
  await expect(door()?.choose("/work")).resolves.toMatchObject({ path: "/work" });
  expect(broadcast).toHaveBeenCalledWith("ui.directorySelected", expect.objectContaining({ path: "/work" }));
});

// CI pass 48: `app.evaluate` is an inspector `Runtime.callFunctionOn`, which V8 runs as an
// interrupt at the next JS function entry — including better-sqlite3's row builder, in the middle
// of some other `.all()`. A door that touched the database on that stack found it busy.
it("chooses on a stack of its own, never on the one it was called from", async () => {
  installE2eDoor({ NODE_ENV: "test" }, false);
  sqlite.inStatement = true;
  const chosen = door()!.choose("/work");
  expect(choose).not.toHaveBeenCalled();
  sqlite.inStatement = false;
  await expect(chosen).resolves.toMatchObject({ path: "/work" });
  expect(broadcast).toHaveBeenCalledOnce();
});

it("is not installed outside a test launch, nor in a packaged app launched as one", () => {
  installE2eDoor({ NODE_ENV: "production" }, false);
  expect(door()).toBeUndefined();
  installE2eDoor({ NODE_ENV: "test" }, true);
  expect(door()).toBeUndefined();
});

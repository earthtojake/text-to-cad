/**
 * `settings.fallbacks` tells the Settings rows two different things: a stored
 * value main refused (read as the default) and a remembered folder that is
 * gone. Only the second may make a row say "no longer exists".
 */
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it, vi } from "vitest";

const rows = vi.hoisted(() => new Map<string, string>());
vi.mock("@main/db/index", () => ({
  db: () => ({
    prepare: () => ({
      all: () => [...rows].map(([key, value]) => ({ key, value })),
      run: (key: string, value: string) => void rows.set(key, value),
    }),
    transaction: (write: () => void) => write,
  }),
}));
const showOpenDialog = vi.hoisted(() => vi.fn(async (..._args: unknown[]) => ({ canceled: true, filePaths: [] as string[] })));
vi.mock("electron", () => ({
  BrowserWindow: { fromWebContents: () => null },
  dialog: { showOpenDialog },
}));

import { dialogsHandlers } from "@main/ipc/dialogs";
import { settingsFallbacks } from "@main/ipc/settings-fallbacks";

const gone = join(tmpdir(), "text-to-cad-no-such-folder");
const ctx = { event: {}, sender: {} } as never;

afterEach(() => {
  rows.clear();
  showOpenDialog.mockClear();
  vi.restoreAllMocks();
});

it("reports a remembered folder that is gone, as gone and not as refused", async () => {
  rows.set("defaultProjectFolder", JSON.stringify(gone));
  rows.set("worktreeRoot", JSON.stringify(tmpdir()));
  expect(await settingsFallbacks()).toEqual({ refused: {}, gone: { defaultProjectFolder: { path: gone, reason: "missing" } } });
});

it("reads a wrong-typed stored folder as the schema fallback, not as gone", async () => {
  rows.set("defaultProjectFolder", JSON.stringify(7));
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(await settingsFallbacks()).toEqual({ refused: { defaultProjectFolder: "7" }, gone: {} });
});

it("a gone folder is reported and the chooser stops opening there, from the same stored value", async () => {
  rows.set("worktreeRoot", JSON.stringify(gone));
  expect((await settingsFallbacks()).gone).toEqual({ worktreeRoot: { path: gone, reason: "missing" } });
  await dialogsHandlers.dialogs.chooseDirectory({ defaultPath: gone }, ctx);
  expect(showOpenDialog.mock.calls[0]?.[0]).not.toHaveProperty("defaultPath", expect.any(String));
});

it("reports a remembered folder that is now a file as gone with the file reason, not as missing", async () => {
  const dir = mkdtempSync(join(tmpdir(), "text-to-cad-fallbacks-"));
  const file = join(dir, "worktrees");
  writeFileSync(file, "");
  try {
    rows.set("worktreeRoot", JSON.stringify(file));
    expect(await settingsFallbacks()).toEqual({ refused: {}, gone: { worktreeRoot: { path: file, reason: "file" } } });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

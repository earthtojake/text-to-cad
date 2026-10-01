/**
 * The e2e suite's way to choose a folder without the native chooser, which
 * Playwright cannot drive. It is not a channel: the renderer has no path in
 * that main resolves on its word. It exists only under `NODE_ENV=test` — the
 * same gate the pre-warms and onboarding use — and only in a development
 * build: an environment variable is something anyone can set in front of a
 * packaged app. It is reached from main's side,
 * `app.evaluate(() => globalThis.__textToCadE2E.choose(dir))`, awaited
 * (`tests/e2e/launch.ts`), exactly as `projects.add` would after a chooser.
 */
import { app } from "electron";

import { projects } from "./db/repositories";
import { broadcast } from "./ipc/register";

export function installE2eDoor(env: NodeJS.ProcessEnv = process.env, packaged = app.isPackaged) {
  if (env.NODE_ENV !== "test" || packaged) return;
  (globalThis as { __textToCadE2E?: unknown }).__textToCadE2E = {
    // Not on the caller's stack: `app.evaluate` is an inspector call, and V8 runs it as an
    // interrupt at the next JS function entry — which can be better-sqlite3's row builder in the
    // middle of another `.all()`, where the connection is busy and `prepare` throws (CI, pass 48).
    // A macrotask starts on an empty stack; `app.evaluate` awaits the promise.
    choose(directory: string): Promise<ReturnType<typeof projects.choose>> {
      return new Promise((resolve, reject) => {
        setImmediate(() => {
          try {
            const selected = projects.choose(directory);
            broadcast("ui.directorySelected", selected);
            resolve(selected);
          } catch (error) {
            reject(error);
          }
        });
      });
    },
  };
}

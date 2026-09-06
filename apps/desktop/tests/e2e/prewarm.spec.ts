import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test } from "@playwright/test";

/**
 * Opening a project starts its CAD runtime before any file asks for it
 * (src/main/cad/index.ts, `warmCad`): the viewer for the project root and
 * the warm build daemon come up on their own, off the critical path of the
 * first CAD file. Main narrates both on stdout — `[viewer] started …` and
 * `[daemon] warming …` — and this test reads that narration, with no file
 * opened at all.
 *
 * Skipped on a machine with no runtime (CI's test job bundles nothing and
 * has no venv): there is nothing to warm, and `runtime.status` says so.
 */

declare const window: {
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    runtime: { status(): Promise<{ state: string }> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");

test("opening a project starts the viewer and the daemon before any file is opened", async () => {
  test.setTimeout(120_000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-prewarm-e2e-"));
  const socketDir = fs.mkdtempSync("/tmp/hc-pw-");
  const { CAD_DESKTOP_PYTHON: _unset, ...inherited } = process.env;
  // A private daemon socket, so the daemon this launch starts is provably
  // its own (and is killed below); Windows names a pipe and keeps the default.
  const env = {
    ...inherited,
    NODE_ENV: "test",
    HARDCORE_NO_PLUGIN_INSTALL: "1",
    // Pre-warming is off under test for every other spec; this one is about it.
    HARDCORE_PREWARM: "1",
    ...(process.platform === "win32" ? {} : { CADGEN_DAEMON_SOCKET: path.join(socketDir, "d.sock") }),
  };
  const lines: string[] = [];
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env,
  });
  app.process().stdout?.on("data", (chunk: Buffer) => lines.push(...String(chunk).split("\n")));
  app.process().stderr?.on("data", (chunk: Buffer) => lines.push(...String(chunk).split("\n")));
  try {
    const page = await app.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    const runtime = await page.evaluate(() => window.hardcore.runtime.status());
    test.skip(runtime.state !== "ready", `no CAD runtime on this machine (${runtime.state})`);

    await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), repoRoot);
    // The strip binds to the project on its own; binding is what warms.
    await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();

    await expect.poll(() => lines.some((line) => /\[viewer\] (started|reused) http:\/\/127\.0\.0\.1:\d+ for /.test(line)), { timeout: 90_000 }).toBe(true);
    await expect.poll(() => lines.some((line) => /\[daemon\] warming /.test(line)), { timeout: 30_000 }).toBe(true);
    // The daemon's own narration goes to the runtime log beside the probe's
    // and the viewer's; "serving" there is the daemon bound and answering,
    // not merely spawned.
    const runtimeLog = path.join(userData, "cad-runtime.log");
    await expect
      .poll(() => (fs.existsSync(runtimeLog) ? fs.readFileSync(runtimeLog, "utf8") : ""), { timeout: 60_000 })
      .toMatch(/\[cadgen-daemon\] pid \d+ serving /);
    // No CAD tab was opened, so nothing asked for the viewer: the surface
    // is absent and the warm was the only reason for the launch.
    await expect(page.locator("[data-cad-surface]")).toHaveCount(0);
  } finally {
    await app.close();
    fs.rmSync(userData, { recursive: true, force: true });
    // The daemon the warm started is detached from the app by design; it is
    // this test's to stop.
    const pidLine = lines.find((line) => /\[daemon\] warming .* \(pid (\d+)\)/.test(line));
    const pid = pidLine ? Number(/\(pid (\d+)\)/.exec(pidLine)?.[1]) : NaN;
    if (Number.isFinite(pid)) {
      try {
        process.kill(pid, "SIGTERM");
      } catch {
        /* already gone (stood down, or idle-exited) */
      }
    }
    fs.rmSync(socketDir, { recursive: true, force: true });
  }
});

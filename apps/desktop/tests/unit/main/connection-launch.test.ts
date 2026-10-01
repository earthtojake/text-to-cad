import type * as ChildProcess from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

import { afterEach, expect, it, vi } from "vitest";

/** A child that never answers: what is under test is how it was spawned. */
const spawn = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", async (original) => ({ ...(await original<typeof ChildProcess>()), spawn }));

import { SessionConnection } from "@main/acp/connection";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import { cleanTempDirs, tempDir } from "./temp-dirs";

afterEach(() => cleanTempDirs());

function fakeChild() {
  return Object.assign(new EventEmitter(), {
    stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), pid: 1, kill: vi.fn(),
  });
}

function launch(
  platform: NodeJS.Platform,
  env: Record<string, string>,
  { command = "npx", args = ["-y", "@agentclientprotocol/codex-acp@latest"] }: { command?: string; args?: string[] } = {},
) {
  spawn.mockReturnValue(fakeChild());
  new SessionConnection({
    sessionId: "s", agentId: "codex", cwd: "/project", env, platform, spawnTerminal: spawnProcessTerminal,
    launch: { command, args, env: {} },
  });
  return spawn.mock.calls.at(-1) as [string, string[], { windowsVerbatimArguments?: boolean }];
}

it("runs a Windows .cmd shim the detector found on PATH through cmd.exe, with its argv escaped", async () => {
  const bin = await tempDir("text-to-cad-win-bin-");
  const shim = path.join(bin, "npx.CMD");
  fs.writeFileSync(shim, "@echo off\n");

  const [command, args, options] = launch("win32", { PATH: bin, PATHEXT: ".EXE;.CMD" });

  expect(command).toBe("cmd.exe");
  expect(args.slice(0, 3)).toEqual(["/d", "/s", "/c"]);
  expect(args[3]).toBe(`"${caret(shim)} ^^^"-y^^^" ^^^"@agentclientprotocol/codex-acp@latest^^^""`);
  expect(options.windowsVerbatimArguments).toBe(true);
});

/** cmd.exe's metacharacters escaped with `^`, once. */
const caret = (text: string) => text.replace(/([()\][%!^"`<>&|;, *?])/g, "^$1");

// npm's global shims (`npx.cmd`, `%AppData%\npm\gemini.cmd`) hand their
// arguments on with `%*`, which cmd parses a second time. Escaped once, an
// argument's `"` survives the first parse and flips the second one's quoting,
// and the `&` after it ends the command.
it("escapes a .cmd shim's argv twice, wherever the shim lives", async () => {
  const bin = await tempDir("text-to-cad-win-npm-");
  const shim = path.join(bin, "gemini.cmd");
  fs.writeFileSync(shim, "@echo off\n");

  const [, args] = launch("win32", { PATH: bin, PATHEXT: ".EXE;.cmd" }, { command: "gemini", args: ['say "hi" & calc'] });

  expect(args[3]).toBe(`"${caret(shim)} ${caret(caret('"say \\"hi\\" & calc"'))}"`);
});

// A launch that names the shim itself (`gemini.cmd`, or its full path) is no
// more runnable without cmd.exe than the bare name: spawn refuses it (EINVAL).
it("runs a launch that already names its .cmd through cmd.exe too", async () => {
  const bin = await tempDir("text-to-cad-win-named-");
  const shim = path.join(bin, "gemini.cmd");
  fs.writeFileSync(shim, "@echo off\n");

  for (const command of [shim, "gemini.cmd"]) {
    const [spawned, args, options] = launch("win32", { PATH: bin, PATHEXT: ".EXE;.CMD" }, { command, args: ["--acp"] });
    expect(spawned).toBe("cmd.exe");
    expect(args).toEqual(["/d", "/s", "/c", `"${caret(shim)} ^^^"--acp^^^""`]);
    expect(options.windowsVerbatimArguments).toBe(true);
  }
});

it("spawns the launch as it is everywhere else", () => {
  const [command, args, options] = launch("darwin", { PATH: "/usr/local/bin" });
  expect([command, args]).toEqual(["npx", ["-y", "@agentclientprotocol/codex-acp@latest"]]);
  expect(options.windowsVerbatimArguments).toBeUndefined();
});

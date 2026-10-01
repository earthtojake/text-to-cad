import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { ENV_BEGIN, ENV_END, captureLoginEnv, loginEnv, parseLoginOutput, processEnv } from "@main/agents/shell-env";

const temps: string[] = [];
afterEach(() => {
  vi.restoreAllMocks();
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

/**
 * A stand-in for `$SHELL`: called as `<shell> -ilc <command>`, it prints what
 * a chatty rc file would (a banner with no trailing newline), runs the command
 * with a known PATH, and prints more on the way out, as a .zlogout might.
 */
function fakeShell(body: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "text-to-cad-shell-"));
  temps.push(dir);
  const file = path.join(dir, "shell");
  fs.writeFileSync(file, `#!/bin/sh\n${body}\n`, { mode: 0o755 });
  return file;
}

describe.skipIf(process.platform === "win32")("capturing the login shell", () => {
  it("keeps the first variable (PATH) when the rc files print before env, and ignores what follows", async () => {
    const shell = fakeShell(
      [
        "printf 'Welcome to your shell\\nlast login: today'",
        'env -i PATH=/fake/bin:/usr/bin:/bin HOME=/home/fake /bin/sh -c "$2"',
        "printf 'bye'",
      ].join("\n"),
    );
    const env = await captureLoginEnv(5_000, shell);
    expect(env.PATH).toBe("/fake/bin:/usr/bin:/bin");
    expect(env.HOME).toBe("/home/fake");
  });

  it("gives agents the login shell's PATH through $SHELL even when an rc file prints a banner first", async () => {
    // What the app calls: `loginEnv`, with the user's $SHELL. The banner has
    // no trailing newline, so without the sentinels it is glued onto the first
    // record (PATH) and the capture falls back to the Dock's environment.
    vi.stubEnv(
      "SHELL",
      fakeShell(
        [
          "printf 'Welcome to your shell\\nlast login: today'",
          'env -i PATH=/fake/bin:/usr/bin:/bin HOME=/home/fake /bin/sh -c "$2"',
          "printf 'bye'",
        ].join("\n"),
      ),
    );
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const env = await loginEnv({ force: true, timeoutMs: 5_000 });
      expect(env.PATH).toBe("/fake/bin:/usr/bin:/bin");
      expect(env.HOME).toBe("/home/fake");
      expect(warn).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("drops a host Claude Code session's variables but keeps the ones the login shell set itself", async () => {
    vi.stubEnv("CLAUDECODE", "1");
    vi.stubEnv("CLAUDE_CODE_OAUTH_TOKEN", "host");
    vi.stubEnv("CLAUDE_CODE_ENTRYPOINT", "cli");
    const shell = fakeShell(
      'env -i PATH=/fake/bin:/usr/bin:/bin CLAUDE_CODE_OAUTH_TOKEN=mine ANTHROPIC_BASE_URL=https://proxy.example /bin/sh -c "$2"',
    );
    try {
      const env = await loginEnv({ force: true, timeoutMs: 5_000, shell });
      // The rc's own value survives; the host's, inherited unchanged, does not.
      expect(env.CLAUDE_CODE_OAUTH_TOKEN).toBe("mine");
      expect(env.ANTHROPIC_BASE_URL).toBe("https://proxy.example");
      expect(env).not.toHaveProperty("CLAUDE_CODE_ENTRYPOINT");
      expect(env).not.toHaveProperty("CLAUDECODE");
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("keeps a Claude variable the rc exports even when the host session inherited the same value from it", async () => {
    // The usual shape: the person's rc exports the token, the terminal that
    // started the host Claude Code session ran that rc, so both hold "same".
    vi.stubEnv("CLAUDECODE", "1");
    vi.stubEnv("CLAUDE_CODE_OAUTH_TOKEN", "same");
    vi.stubEnv("ANTHROPIC_BASE_URL", "https://proxy.example");
    const shell = fakeShell(
      'CLAUDE_CODE_OAUTH_TOKEN=same ANTHROPIC_BASE_URL=https://proxy.example /bin/sh -c "$2"',
    );
    try {
      const env = await loginEnv({ force: true, timeoutMs: 5_000, shell });
      expect(env.CLAUDE_CODE_OAUTH_TOKEN).toBe("same");
      expect(env.ANTHROPIC_BASE_URL).toBe("https://proxy.example");
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("strips a host variable the rc does not set, and CLAUDECODE unless the rc sets it", async () => {
    vi.stubEnv("CLAUDECODE", "1");
    vi.stubEnv("CLAUDE_CODE_ENTRYPOINT", "cli");
    vi.stubEnv("ANTHROPIC_BASE_URL", "https://host.example");
    // A shell that passes its inherited environment through untouched.
    const plain = fakeShell('/bin/sh -c "$2"');
    const sets = fakeShell('CLAUDECODE=rc /bin/sh -c "$2"');
    try {
      const env = await loginEnv({ force: true, timeoutMs: 5_000, shell: plain });
      expect(env).not.toHaveProperty("CLAUDE_CODE_ENTRYPOINT");
      expect(env).not.toHaveProperty("ANTHROPIC_BASE_URL");
      expect(env).not.toHaveProperty("CLAUDECODE");
      expect((await loginEnv({ force: true, timeoutMs: 5_000, shell: sets })).CLAUDECODE).toBe("rc");
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("falls back to process.env with a warning when the shell is too slow", async () => {
    const shell = fakeShell("sleep 5");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const env = await loginEnv({ force: true, timeoutMs: 200, shell });
    expect(env.PATH).toBe(processEnv().PATH);
    expect(warn).toHaveBeenCalledWith(expect.stringMatching(/login shell.*process environment/i));
  });
});

describe("the login shell's output", () => {
  it("reads only between the sentinels", () => {
    const output = `motd\nno newline${"\n"}${ENV_BEGIN}\nPATH=/a:/b\0HOME=/h\0${"\n"}${ENV_END}\ngoodbye`;
    expect(parseLoginOutput(output)).toEqual({ PATH: "/a:/b", HOME: "/h" });
  });

  it("reads plain env output between the sentinels", () => {
    expect(parseLoginOutput(`noise${"\n"}${ENV_BEGIN}\nPATH=/a\nHOME=/h\n${"\n"}${ENV_END}\n`)).toEqual({
      PATH: "/a",
      HOME: "/h",
    });
  });
});

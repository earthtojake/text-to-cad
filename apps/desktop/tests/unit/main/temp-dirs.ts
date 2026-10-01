/**
 * Scratch directories for the tests that spawn the fake agent, and their
 * removal. Each test file gets its own copy of this module (vitest isolates
 * modules per file), so `cleanTempDirs` removes only that file's directories.
 *
 * Call `cleanTempDirs` after whatever the test started has stopped: an adapter
 * still running can write into its cwd (`fs/write_text_file` makes parent
 * directories), which would put the directory back.
 */
import fs from "node:fs";
import { mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const made: string[] = [];

/** `mkdtemp` under the OS temp directory, resolved, and remembered for `cleanTempDirs`. */
export async function tempDir(prefix: string): Promise<string> {
  const dir = await realpath(await mkdtemp(path.join(os.tmpdir(), prefix)));
  made.push(dir);
  return dir;
}

/** Writable first, so a read-only file or directory cannot stop the removal. */
export function removeTree(dir: string): void {
  const stack = [dir];
  while (stack.length > 0) {
    const current = stack.pop()!;
    let entries: fs.Dirent[];
    try {
      fs.chmodSync(current, 0o755);
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else if (!entry.isSymbolicLink()) {
        try {
          fs.chmodSync(full, 0o644);
        } catch {
          /* removed below regardless */
        }
      }
    }
  }
  fs.rmSync(dir, { recursive: true, force: true });
}

/** Remove every directory `tempDir` made in this file so far. */
export function cleanTempDirs(): void {
  for (const dir of made.splice(0)) {
    removeTree(dir);
  }
}

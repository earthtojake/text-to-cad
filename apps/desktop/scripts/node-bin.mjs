/**
 * A dependency's command-line tool, run as `node <its JS entry>`.
 *
 * Not `npx <tool>` and not `node_modules/.bin/<tool>`: on Windows both are
 * `.cmd` shims, and Node (18.20.2, 20.12.2, 22 and later — the CVE-2024-27980
 * fix) refuses to spawn a `.cmd` or `.bat` without a shell, with EINVAL.
 * A shell brings its own quoting to every argument; the tool's own entry file
 * run by this very Node needs neither, and behaves the same on every host.
 */
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);

/** The file a package's `bin` names for `name`, resolved from this app. */
export function binEntry(pkg, name = pkg) {
  const manifestPath = require.resolve(`${pkg}/package.json`);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const bin = typeof manifest.bin === "string" ? manifest.bin : manifest.bin?.[name];
  if (!bin) {
    throw new Error(`${pkg} has no \`${name}\` command in its package.json bin`);
  }
  return path.join(path.dirname(manifestPath), bin);
}

/**
 * `[command, args]` for `spawnSync`: this Node, the tool's entry, then `args`.
 *
 * @returns {[string, string[]]}
 */
export function nodeTool(pkg, args, name = pkg) {
  return [process.execPath, [binEntry(pkg, name), ...args]];
}

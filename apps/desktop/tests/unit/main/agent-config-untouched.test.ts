/**
 * AGENTS.md: nothing is installed into an agent's configuration — no write
 * to `~/.claude` or `~/.codex`. The cheapest guard is that main never builds
 * a path from the home directory into either: `homedir()` next to `.claude`
 * or `.codex` in one expression. (The sign-in probe reads fixed relative
 * files through an injected `homeDir`, and names no `homedir()` call beside
 * them.)
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const mainRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "src", "main");

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sources(full);
    return /\.(ts|mts|mjs|js)$/.test(entry.name) ? [full] : [];
  });
}

const code = (file: string) =>
  readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

/** `homedir()` and a `.claude`/`.codex` segment within one statement, either order. */
const JOINED = /homedir\(\)[^;]{0,200}?\.(claude|codex)\b|\.(claude|codex)\b[^;]{0,200}?homedir\(\)/;

it("never joins homedir() with .claude or .codex in src/main", () => {
  const offenders = sources(mainRoot).flatMap((file) => {
    const match = JOINED.exec(code(file));
    return match ? [`${path.relative(mainRoot, file)}: ${match[0].replace(/\s+/g, " ")}`] : [];
  });
  expect(offenders.join("\n"), "paths from the home directory into an agent's configuration").toBe("");
});

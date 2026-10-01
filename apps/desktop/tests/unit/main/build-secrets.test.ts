/**
 * AGENTS.md: nothing reads `process.env` for a build-time secret. The
 * Aptabase key is compiled in as `__APTABASE_KEY__`; a key the launcher can
 * set is a key anyone can redirect.
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

/** Source with comments blanked, so a comment naming the variable is not a read. */
const code = (file: string) =>
  readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

it("never reads an Aptabase key from process.env in src/main", () => {
  const offenders = sources(mainRoot).flatMap((file) =>
    code(file)
      .split("\n")
      .filter((line) => /process\.env/.test(line) && /APTABASE/i.test(line))
      .map((line) => `${path.relative(mainRoot, file)}: ${line.trim()}`),
  );
  expect(offenders.join("\n"), "process.env reads of an Aptabase key").toBe("");
});

it("takes the key from the compiled-in __APTABASE_KEY__", () => {
  expect(code(path.join(mainRoot, "telemetry.ts"))).toMatch(/=\s*__APTABASE_KEY__\b/);
});

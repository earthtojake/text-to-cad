/**
 * The README's screenshot paragraph ("What the specs capture, and nothing
 * else") and the e2e specs name the same shots: every PNG a spec writes
 * (`shoot…(` or `outputPath(`) is named there, and every shot named there is
 * one a spec writes or one of the committed `tests/e2e/__screenshots__/`.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const e2eRoot = path.join(appRoot, "tests", "e2e");

/** Backticked words in that paragraph that are prose, not shots. */
const PROSE = new Set(["limits"]);

/** A spec's shot name as a pattern: `settings-${slug}.png` is `settings-<anything>`. */
type Shot = { spec: string; name: string; pattern: RegExp };

const shots: Shot[] = readdirSync(e2eRoot)
  .filter((name) => name.endsWith(".ts"))
  .flatMap((spec) =>
    [...readFileSync(path.join(e2eRoot, spec), "utf8").matchAll(/\b(?:shoot\w*|outputPath)\(\s*(["'`])([^"'`]+?)\.png\1/g)].map(
      (match) => {
        const name = match[2]!;
        const source = name
          .split(/\$\{[^}]*\}/)
          .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
          .join("[^`\\s]+");
        return { spec, name, pattern: new RegExp(`^${source}$`) };
      },
    ),
  );

const readme = readFileSync(path.join(appRoot, "README.md"), "utf8");
const start = readme.indexOf("What the specs capture");
const end = readme.indexOf("is older evidence no spec", start);
const paragraph = start >= 0 && end > start ? readme.slice(start, end) : "";
/** Backticked tokens shaped like a shot name (`file-cad`, `settings-<page>`, `terminal`). */
const named = [...paragraph.matchAll(/`([a-z0-9<>]+(?:-[a-z0-9<>]+)*)`/g)].map((match) => match[1]!).filter((token) => !PROSE.has(token));

it("finds the paragraph and the specs' shots", () => {
  expect(paragraph, "README's screenshot paragraph").not.toBe("");
  expect(shots.length).toBeGreaterThan(20);
});

it("names every shot a spec writes", () => {
  const missing = shots
    .filter((shot) => !named.some((token) => shot.pattern.test(token) || token === shot.name))
    .map((shot) => `${shot.spec}: ${shot.name}.png`);
  expect(missing.join("\n"), "shots the e2e writes that README does not name").toBe("");
});

it("names no shot that no spec writes", () => {
  const committed = path.join(e2eRoot, "__screenshots__");
  const stale = named.filter((token) => {
    const placeholder = token.replace(/<[^>]+>/g, "PLACEHOLDER");
    return (
      !shots.some((shot) => shot.pattern.test(token) || shot.pattern.test(placeholder)) &&
      !existsSync(path.join(committed, `${token}.png`))
    );
  });
  expect(stale.join("\n"), "README shots no spec writes").toBe("");
});

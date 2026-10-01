/**
 * AGENTS.md: `package.json` stays at version `0.0.0` (the repository's
 * `VERSION` is stamped in at build time), and every dependency is an exact
 * version — the one exception is the workspace links, which npm spells `*`.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const manifest = JSON.parse(readFileSync(path.join(appRoot, "package.json"), "utf8")) as {
  version: string;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
};

const WORKSPACE_LINKS = new Set(["@text-to-cad/core", "@text-to-cad/ui"]);
const EXACT = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

it("stays at version 0.0.0", () => {
  expect(manifest.version).toBe("0.0.0");
});

it("pins every dependency to an exact version, workspace links aside", () => {
  const offenders = (["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"] as const).flatMap(
    (field) =>
      Object.entries(manifest[field] ?? {}).flatMap(([name, spec]) => {
        if (WORKSPACE_LINKS.has(name)) return spec === "*" ? [] : [`${field} ${name}: ${spec} (a workspace link is "*")`];
        return EXACT.test(spec) ? [] : [`${field} ${name}: ${spec}`];
      }),
  );
  expect(offenders.join("\n"), "dependency specifiers that are not exact versions").toBe("");
});

it("declares the packages math.ts imports, not only hoists them", () => {
  // `katex/dist/katex.min.css` is imported by `src/renderer/lib/math.ts`; the
  // package arrived as a transitive dependency of `@streamdown/math`, which is
  // one hoist away from not being there.
  const source = readFileSync(path.join(appRoot, "src", "renderer", "lib", "math.ts"), "utf8");
  const imported = [...source.matchAll(/(?:from|import)\s*\(?\s*["']((?:@[\w-]+\/)?[\w-]+)[^"']*["']/g)].map((match) => match[1]!);
  const declared = { ...manifest.dependencies, ...manifest.devDependencies };
  const undeclared = imported.filter((name) => !name.startsWith("@renderer") && !name.startsWith("@shared") && !(name in declared) && name !== "react");
  expect(undeclared.join(", "), "packages imported by math.ts and missing from package.json").toBe("");
});

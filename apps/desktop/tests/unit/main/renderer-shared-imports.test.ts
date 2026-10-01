/**
 * AGENTS.md: the renderer imports from `src/main` never, and from `src/shared`
 * only types and the pure modules it names. A value import from any other
 * shared module is a module that may grow a Node import and take the page
 * down with it. Type-only imports (`import type`, or braces whose every
 * specifier is `type`) are erased and always allowed.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const rendererRoot = path.join(appRoot, "src", "renderer");
const sharedRoot = path.join(appRoot, "src", "shared");
const mainRoot = path.join(appRoot, "src", "main");

/** The shared modules the renderer may take values from (AGENTS.md), without extension. */
const VALUE_ALLOWLIST = new Set([
  "types",
  "acp/options",
  "acp/reduce",
  "cad-refs",
  "terminal-replies",
  "titlebar",
  "ipc/errors",
  "image-cap",
]);

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sources(full);
    return /\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith(".d.ts") ? [full] : [];
  });
}

/** The module a specifier names, as an absolute path without extension, or null for a package. */
function resolveSpecifier(from: string, specifier: string): string | null {
  const aliases: Record<string, string> = { "@shared/": sharedRoot, "@main/": mainRoot, "@renderer/": rendererRoot };
  for (const [prefix, root] of Object.entries(aliases)) {
    if (specifier.startsWith(prefix)) return path.join(root, specifier.slice(prefix.length));
  }
  if (specifier === "@shared") return sharedRoot;
  if (specifier.startsWith(".")) return path.resolve(path.dirname(from), specifier);
  return null;
}

/** Whether an `import …`/`export …` clause brings in only types. */
function typeOnly(keyword: string, clause: string): boolean {
  if (/^type\s/.test(clause)) return true;
  // `import X, { … }` or `import * as X` carry a value binding.
  const braces = /^\{([\s\S]*)\}$/.exec(clause.trim());
  if (!braces) return false;
  const specifiers = braces[1]!.split(",").map((part) => part.trim()).filter(Boolean);
  return keyword !== "" && specifiers.length > 0 && specifiers.every((part) => /^type\s/.test(part));
}

type Found = { file: string; specifier: string; typeOnly: boolean };

/** Every static import/export-from, side-effect import and dynamic import in a file. */
function imports(file: string): Found[] {
  const text = readFileSync(file, "utf8");
  const found: Found[] = [];
  for (const match of text.matchAll(/(?:^|[\n;])\s*(import|export)\s+([^;]*?)\s+from\s+["']([^"']+)["']/g)) {
    found.push({ file, specifier: match[3]!, typeOnly: typeOnly(match[1]!, match[2]!) });
  }
  for (const match of text.matchAll(/(?:^|[\n;])\s*import\s+["']([^"']+)["']/g)) {
    found.push({ file, specifier: match[1]!, typeOnly: false });
  }
  for (const match of text.matchAll(/\bimport\(\s*["']([^"']+)["']\s*\)/g)) {
    // `typeof import("…")` in a type position is erased.
    const before = text.slice(Math.max(0, match.index - 7), match.index);
    found.push({ file, specifier: match[1]!, typeOnly: /typeof\s$/.test(before) });
  }
  return found;
}

const all = sources(rendererRoot).flatMap(imports);

it("sees the renderer's imports of src/shared", () => {
  // A scanner that finds nothing would pass every rule below.
  expect(all.filter((found) => found.specifier.startsWith("@shared")).length).toBeGreaterThan(20);
});

it("takes values from src/shared only through the allowlisted modules", () => {
  const offenders = all
    .filter((found) => !found.typeOnly)
    .flatMap((found) => {
      const target = resolveSpecifier(found.file, found.specifier);
      if (!target || !target.startsWith(sharedRoot + path.sep)) return [];
      const module = path.relative(sharedRoot, target).split(path.sep).join("/").replace(/\.(ts|tsx)$/, "").replace(/\/index$/, "");
      return VALUE_ALLOWLIST.has(module) ? [] : [`${path.relative(appRoot, found.file)} → ${found.specifier}`];
    });
  expect(offenders.join("\n"), "renderer value imports from shared modules outside the AGENTS.md allowlist").toBe("");
});

it("imports nothing from src/main", () => {
  const offenders = all
    .filter((found) => {
      const target = resolveSpecifier(found.file, found.specifier);
      return target !== null && (target === mainRoot || target.startsWith(mainRoot + path.sep));
    })
    .map((found) => `${path.relative(appRoot, found.file)} → ${found.specifier}`);
  expect(offenders.join("\n"), "renderer imports from src/main").toBe("");
});

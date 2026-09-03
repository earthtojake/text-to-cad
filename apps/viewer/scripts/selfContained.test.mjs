// The client is a package with a boundary: it imports cadgen-js by NAME (resolved
// by the vite alias / the `file:` dependency) and nothing else from outside its
// own directory. A relative specifier that climbs out of the app root is a
// reach into a sibling package's internals, which this fence refuses -- the
// same law tests/python/global/test_package_boundaries.py holds for markdown.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SKIPPED_DIRS = new Set([
  "node_modules",
  "dist",
  "dist-verify",
  ".vite",
  ".vercel",
  "coverage",
  "tmp",
  "__pycache__",
  ".pytest_cache",
  ".git",
]);

function collectFiles(dir, matches, files = []) {
  if (!fs.existsSync(dir)) {
    return files;
  }
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIPPED_DIRS.has(entry.name)) {
      continue;
    }
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collectFiles(entryPath, matches, files);
    } else if (matches.test(entry.name)) {
      files.push(entryPath);
    }
  }
  return files;
}

function escapesAppRoot(resolvedPath) {
  const relative = path.relative(appRoot, resolvedPath);
  return relative.startsWith("..") || path.isAbsolute(relative);
}

test("relative module specifiers never resolve above the app root", () => {
  // `from "x"`, `import "x"`, `import("x")`, and `require("x")` — relative ones only.
  const specifierPattern =
    /(?:\bfrom\s*|\bimport\s*|\brequire\s*\(\s*|\bimport\s*\(\s*)["'](\.[^"']*)["']/gu;
  const offenders = [];
  for (const filePath of collectFiles(appRoot, /\.[cm]?jsx?$/u)) {
    const source = fs.readFileSync(filePath, "utf8");
    for (const match of source.matchAll(specifierPattern)) {
      const resolved = path.resolve(path.dirname(filePath), match[1]);
      if (escapesAppRoot(resolved)) {
        offenders.push(`${path.relative(appRoot, filePath)} -> ${match[1]}`);
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `imports must stay inside the viewer app root:\n  ${offenders.join("\n  ")}`
  );
});

test("markdown relative links resolve to files inside the app root", () => {
  // Inline links only: `[text](target)`. Skips URLs, anchors, and mailto.
  const linkPattern = /\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/gu;
  const offenders = [];
  for (const filePath of collectFiles(appRoot, /\.md$/u)) {
    const source = fs.readFileSync(filePath, "utf8");
    for (const match of source.matchAll(linkPattern)) {
      const target = match[1];
      if (/^(?:[a-z][a-z0-9+.-]*:|#|<)/iu.test(target)) {
        continue;
      }
      const resolved = path.resolve(path.dirname(filePath), target.split("#")[0]);
      const label = `${path.relative(appRoot, filePath)} -> ${target}`;
      if (escapesAppRoot(resolved)) {
        offenders.push(`${label} (escapes app root)`);
      } else if (!fs.existsSync(resolved)) {
        offenders.push(`${label} (missing)`);
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `markdown links must resolve inside the viewer app root:\n  ${offenders.join("\n  ")}`
  );
});

test("package.json scripts never reach above the app root", () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(appRoot, "package.json"), "utf8"));
  const offenders = Object.entries(packageJson.scripts || {})
    .filter(([, command]) => /(?:^|[\s"'=])\.\.\//u.test(String(command)))
    .map(([name, command]) => `${name}: ${command}`);
  assert.deepEqual(
    offenders,
    [],
    `package.json scripts must run from inside the viewer app root:\n  ${offenders.join("\n  ")}`
  );
});

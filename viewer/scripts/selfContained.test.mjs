// This app ships two ways: in place inside the text-to-cad workbench, and as a
// standalone checkout mirrored to its own repo (scripts/viewer/sync-cad-viewer-repo.sh).
// The mirror is a straight copy — nothing rewrites paths on the way out — so any
// reference that reaches above this directory is broken the moment it ships.
// These tests are that fence. `packages/*` is excluded: it is a vendored
// dependency (a symlink in the workbench, a real copy in the mirror), so it owns
// its own internal references.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SKIPPED_DIRS = new Set([
  "node_modules",
  "packages",
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

test("markdown never names a path outside the app root", () => {
  // Broader than the link check above: this also covers prose, inline code, and
  // fenced blocks. Markdown under this directory may only refer to itself, so a
  // `../` that climbs out is unaddressable in a standalone checkout, and a
  // `viewer/`-prefixed path is the workbench spelling of an in-app path.
  // \x60 is a backtick: escaping one inside String.raw would leave the
  // backslash in place, and `\`` is an invalid escape in a unicode class.
  const boundary = String.raw`(?:^|[\s\x60("'\[|])`;
  const pathBody = String.raw`[A-Za-z0-9_.@/-]`;
  const climbingPattern = new RegExp(`${boundary}((?:\\.\\./)+${pathBody}*)`, "gu");
  const workbenchPrefixPattern = new RegExp(`${boundary}(viewer/${pathBody}+)`, "gu");
  const offenders = [];
  for (const filePath of collectFiles(appRoot, /\.md$/u)) {
    const source = fs.readFileSync(filePath, "utf8");
    const label = path.relative(appRoot, filePath);
    for (const match of source.matchAll(climbingPattern)) {
      const resolved = path.resolve(path.dirname(filePath), match[1]);
      if (escapesAppRoot(resolved)) {
        offenders.push(`${label} -> ${match[1]} (climbs out of the app root)`);
      }
    }
    for (const match of source.matchAll(workbenchPrefixPattern)) {
      offenders.push(`${label} -> ${match[1]} (drop the workbench "viewer/" prefix)`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `markdown under the viewer app root may only refer to itself:\n  ${offenders.join("\n  ")}`
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

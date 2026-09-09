// Runtime imports stay inside the app or use shared packages' public exports.
// Development documentation may link to the packages and repository guidance it
// describes. The separate cadgen Markdown isolation check protects the wheel's
// ships-alone documentation; this private workspace app is not that distribution.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "../..");
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

function escapesRoot(root, resolvedPath) {
  const relative = path.relative(root, resolvedPath);
  return relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative);
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
      if (escapesRoot(appRoot, resolved)) {
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

test("markdown relative links resolve inside the repository", () => {
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
      if (escapesRoot(repoRoot, resolved)) {
        offenders.push(`${label} (escapes repository)`);
      } else if (!fs.existsSync(resolved)) {
        offenders.push(`${label} (missing)`);
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `markdown links must resolve inside the repository:\n  ${offenders.join("\n  ")}`
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

/**
 * Every backticked `src/…`, `tests/…`, `scripts/…` or `docs/…` path in the
 * app's prose — README.md, AGENTS.md, docs/*.md, and the comments of the
 * modules whose headers point at other files — names something on disk. A
 * rename that leaves a sentence pointing at nothing is how a doc starts to
 * describe a different app.
 *
 * `{a,b}` expands; a `<placeholder>` or `*` segment checks the directory
 * before it; a `:line` suffix is dropped; a name without its extension
 * (`tests/unit/renderer/file-renderers`) matches the file it is the stem of.
 * A path is looked up from the app root, the document's own folder, then the
 * repository root (the e2e reads its STEP fixture from the repository's
 * `tests/`).
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");

/** Backticked paths that are examples in an argument, not references to this tree. */
const EXAMPLES = new Set([
  // fs.ts: a symlink `docs -> ~/.ssh` cannot carry a new file out of the root.
  "docs/authorized_keys",
]);

/** Modules whose comments send the reader to other files. */
const MODULES = [
  "src/renderer/lib/shortcuts.ts",
  "src/main/projects/workspace.ts",
  "src/main/projects/git.ts",
  "src/main/ipc/index.ts",
  "src/main/integrations/skills.ts",
  "src/main/acp/sessions.ts",
  "src/main/explorer/fs.ts",
  "src/main/index.ts",
  "src/main/quit-deadline.ts",
  "src/main/test-door.ts",
  "src/main/ipc/git.ts",
  "src/main/integrations/actions.ts",
  "src/main/acp/connection.ts",
];

/** The workspace packages' own docs, outside the app: paths in them are from the package root, the app's or the repository's. */
const PACKAGE_DOCS = ["packages/ui", "packages/core"].flatMap((pkg) =>
  readdirSync(path.join(repoRoot, pkg, "docs"))
    .filter((name) => name.endsWith(".md"))
    .map((name) => `${pkg}/docs/${name}`),
);

const DOCUMENTS = [
  "README.md",
  "AGENTS.md",
  ...readdirSync(path.join(appRoot, "docs"))
    .filter((name) => name.endsWith(".md"))
    .map((name) => `docs/${name}`),
];

/** `a/{b,c}/d` → `a/b/d`, `a/c/d`, for any number of groups. */
function expand(pattern: string): string[] {
  const match = /\{([^{}]*)\}/.exec(pattern);
  if (!match) return [pattern];
  return match[1]!
    .split(",")
    .flatMap((choice) => expand(pattern.slice(0, match.index) + choice + pattern.slice(match.index + match[0].length)));
}

/** The part of a path that has to exist: everything before a placeholder or glob segment. */
function concrete(candidate: string): string {
  const segments = candidate.split("/");
  const open = segments.findIndex((segment) => /[<>*]/.test(segment));
  return open === -1 ? candidate : segments.slice(0, open).join("/") + "/";
}

const commentsOf = (text: string) =>
  [...text.matchAll(/\/\*[\s\S]*?\*\/|(?:^|[^:"'`])\/\/.*$/gm)].map((match) => match[0]).join("\n");

const PATH = /`((?:apps\/desktop\/)?(?:src|tests|scripts|docs)\/[^`\s]*)`/g;

/** A file or directory at `full`, or a file whose name is `full`'s basename plus an extension. */
function onDisk(full: string): boolean {
  if (existsSync(full)) return true;
  const dir = path.dirname(full);
  const stem = path.basename(full);
  return existsSync(dir) && readdirSync(dir).some((name) => name.startsWith(`${stem}.`));
}

function missingIn(source: string, text: string, from = appRoot): string[] {
  const roots = [from, appRoot, path.dirname(path.join(from, source)), repoRoot];
  return [...text.matchAll(PATH)].flatMap((match) => {
    const raw = match[1]!.replace(/^apps\/desktop\//, "").replace(/:\d+(?:-\d+)?$/, "").replace(/[.,;:]$/, "");
    if (EXAMPLES.has(raw)) return [];
    return expand(raw)
      .map(concrete)
      .filter((candidate) => !roots.some((root) => onDisk(path.join(root, candidate))))
      .map((candidate) => `${source}: ${match[1]}${candidate === raw ? "" : ` (${candidate})`}`);
  });
}

it("reads the documents and modules it checks", () => {
  for (const file of [...DOCUMENTS, ...MODULES]) expect(existsSync(path.join(appRoot, file)), file).toBe(true);
  expect(DOCUMENTS.length).toBeGreaterThan(3);
});

it("names only paths that exist, in README, AGENTS and docs", () => {
  const missing = DOCUMENTS.flatMap((doc) => missingIn(doc, readFileSync(path.join(appRoot, doc), "utf8")));
  expect(missing.join("\n"), "backticked paths in the docs that are not on disk").toBe("");
});

it("names only paths that exist, in the modules' comments", () => {
  const missing = MODULES.flatMap((file) => missingIn(file, commentsOf(readFileSync(path.join(appRoot, file), "utf8"))));
  expect(missing.join("\n"), "backticked paths in module comments that are not on disk").toBe("");
});

it("names only paths that exist, in the packages' docs", () => {
  expect(PACKAGE_DOCS.length).toBeGreaterThan(10);
  const missing = PACKAGE_DOCS.flatMap((doc) =>
    missingIn(doc, readFileSync(path.join(repoRoot, doc), "utf8"), path.join(repoRoot, doc.split("/docs/")[0]!)),
  );
  expect(missing.join("\n"), "backticked paths in packages/*/docs that are not on disk").toBe("");
});

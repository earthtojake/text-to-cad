/**
 * The filesystem behind the explorer's file tab: the tree, the reads and
 * writes, and one watcher per project root.
 *
 * Two rules run through everything here.
 *
 * **Nothing escapes a root.** Every path the renderer sends is resolved
 * against the project root it names and rejected if it lands outside — after
 * `realpath`, so a symlink cannot be used as a door. The renderer is a browser
 * context; a path it sends is untrusted input, not a fact.
 *
 * **A directory is listed one level at a time.** The tree is lazy: expanding a
 * folder is a request. A recursive walk of a repository with `node_modules` in
 * it is seconds of work and megabytes of payload for a pane that shows thirty
 * rows.
 *
 * Electron is deliberately not imported: this module is plain Node, so
 * `tests/unit/main/explorer-fs.test.ts` can run it.
 */
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import ignore, { type Ignore } from "ignore";

/* -------------------------------------------------------------------------- */
/* What a tree row is                                                          */
/* -------------------------------------------------------------------------- */

export type DirEntry = {
  /** Root-relative, POSIX separators — the id the renderer keys rows by. */
  path: string;
  name: string;
  kind: "file" | "directory";
  /** Bytes, for files. Directories report 0. */
  size: number;
  /** Modification time in unix milliseconds. */
  modifiedAt: number;
  /** True when the entry is a symlink (resolved before its kind is read). */
  symlink: boolean;
};

export type FileKind = "text" | "image" | "pdf" | "cad" | "binary";

export type FileStat = {
  path: string;
  name: string;
  kind: "file" | "directory";
  size: number;
  modifiedAt: number;
  /** Which renderer the file tab should reach for. */
  fileKind: FileKind;
  /** Best-effort media type, `application/octet-stream` when unknown. */
  mime: string;
  /** Lowercase extension without the dot, `""` when there is none. */
  extension: string;
};

/* -------------------------------------------------------------------------- */
/* Ignores                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Directories no file tree should ever walk into, `.gitignore` or not.
 *
 * `.git` is the obvious one. The rest are the build and dependency trees that
 * are ignored in practice in every repository but not always in the file: a
 * tree that lists `node_modules` is a tree nobody scrolls.
 */
export const ALWAYS_IGNORED = [
  ".git",
  ".hg",
  ".svn",
  ".DS_Store",
  "node_modules",
  "__pycache__",
  ".venv",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  ".turbo",
  ".next",
  ".vite",
  ".gradle",
] as const;

const ALWAYS_IGNORED_SET: ReadonlySet<string> = new Set(ALWAYS_IGNORED);

/**
 * The ignore rules that apply inside one root.
 *
 * Only the root's own `.gitignore` and `.git/info/exclude` are read — nested
 * `.gitignore` files are not, which is a deliberate simplification: honouring
 * them properly means re-reading a file per directory on every expansion, and
 * a repository whose nested rules hide something the tree still shows is a
 * cosmetic miss, not a correctness one.
 */
export class IgnoreRules {
  private constructor(private readonly matcher: Ignore | null) {}

  /** Rules with nothing but the always-ignored list. */
  static none(): IgnoreRules {
    return new IgnoreRules(null);
  }

  /** Rules built from explicit patterns — the shape the tests use. */
  static fromPatterns(patterns: readonly string[]): IgnoreRules {
    const usable = patterns.filter((line) => line.trim() !== "" && !line.startsWith("#"));
    return new IgnoreRules(usable.length > 0 ? ignore().add([...usable]) : null);
  }

  /** Rules read off disk. A root with no ignore file is not an error. */
  static async read(root: string): Promise<IgnoreRules> {
    const sources = [
      path.join(root, ".gitignore"),
      path.join(root, ".git", "info", "exclude"),
    ];
    const patterns: string[] = [];
    for (const source of sources) {
      const text = await fs.readFile(source, "utf8").catch(() => null);
      if (text !== null) {
        patterns.push(...text.split(/\r?\n/));
      }
    }
    return IgnoreRules.fromPatterns(patterns);
  }

  /**
   * Should this entry be hidden?
   *
   * `relative` is root-relative with POSIX separators. Directories are tested
   * with a trailing slash as well, because `build/` in a `.gitignore` matches
   * the directory and not a file of the same name.
   */
  ignores(relative: string, isDirectory: boolean): boolean {
    if (relative === "" || relative === ".") {
      return false;
    }
    if (relative.split("/").some((segment) => ALWAYS_IGNORED_SET.has(segment))) {
      return true;
    }
    if (!this.matcher) {
      return false;
    }
    return this.matcher.ignores(isDirectory ? `${relative}/` : relative);
  }
}

/* -------------------------------------------------------------------------- */
/* Containment                                                                 */
/* -------------------------------------------------------------------------- */

export class FsError extends Error {
  override readonly name = "FsError";
}

/** POSIX-separated, root-relative form of an absolute path. */
export function toRelative(root: string, target: string): string {
  const relative = path.relative(root, target);
  return relative === "" ? "" : relative.split(path.sep).join("/");
}

/** True when `target` is `root` or lives under it. */
export function isInside(root: string, target: string): boolean {
  if (target === root) {
    return true;
  }
  const relative = path.relative(root, target);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

/**
 * Resolve a renderer-supplied path against a root and refuse anything outside.
 *
 * Both halves are resolved with `realpath` where they exist, so a symlink in
 * the root that points at `/etc` is caught. A path that does not exist yet (a
 * write to a new file) is checked lexically against the real root instead —
 * its parent is what has to be inside.
 */
export async function resolveInRoot(root: string, target: string): Promise<string> {
  const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
  const absolute = path.isAbsolute(target) ? target : path.join(realRoot, target);
  const real = await fs.realpath(absolute).catch(() => null);
  const resolved = real ?? path.resolve(absolute);
  if (!isInside(realRoot, resolved)) {
    throw new FsError("path is outside the project");
  }
  return resolved;
}

/* -------------------------------------------------------------------------- */
/* Type detection                                                              */
/* -------------------------------------------------------------------------- */

/**
 * The file types the explorer renders. This is the one table: the extension
 * decides the renderer and the media type together, so a `.step` cannot end up
 * routed to Monaco while claiming to be `model/step`.
 */
const TYPES: ReadonlyArray<readonly [FileKind, string, readonly string[]]> = [
  ["image", "image/png", ["png"]],
  ["image", "image/jpeg", ["jpg", "jpeg"]],
  ["image", "image/gif", ["gif"]],
  ["image", "image/webp", ["webp"]],
  ["image", "image/svg+xml", ["svg"]],
  ["image", "image/bmp", ["bmp"]],
  ["image", "image/x-icon", ["ico"]],
  ["image", "image/avif", ["avif"]],
  ["pdf", "application/pdf", ["pdf"]],
  // The nine extensions the CAD Viewer's file surface understands (plan §3).
  ["cad", "model/step", ["step", "stp"]],
  ["cad", "model/gltf-binary", ["glb"]],
  ["cad", "model/stl", ["stl"]],
  ["cad", "model/3mf", ["3mf"]],
  ["cad", "image/vnd.dxf", ["dxf"]],
  ["cad", "application/xml", ["urdf", "srdf", "sdf"]],
  ["binary", "application/zip", ["zip", "gz", "tgz", "bz2", "xz", "7z", "rar"]],
  ["binary", "font/woff2", ["woff", "woff2", "ttf", "otf", "eot"]],
  ["binary", "video/mp4", ["mp4", "mov", "webm", "avi", "mkv"]],
  ["binary", "audio/mpeg", ["mp3", "wav", "flac", "aac", "ogg"]],
  ["binary", "application/octet-stream", ["wasm", "so", "dylib", "dll", "exe", "node", "pyc"]],
  ["text", "text/markdown", ["md", "markdown", "mdx"]],
  ["text", "application/json", ["json", "jsonc", "json5", "ipynb"]],
  ["text", "text/html", ["html", "htm"]],
  ["text", "text/css", ["css", "scss", "sass", "less"]],
  ["text", "text/yaml", ["yml", "yaml"]],
  ["text", "text/x-toml", ["toml"]],
  ["text", "text/x-python", ["py", "pyi"]],
  ["text", "text/typescript", ["ts", "tsx", "mts", "cts"]],
  ["text", "text/javascript", ["js", "jsx", "mjs", "cjs"]],
  ["text", "text/x-rust", ["rs"]],
  ["text", "text/x-go", ["go"]],
  ["text", "text/x-c", ["c", "h", "cc", "cpp", "hpp", "cxx"]],
  ["text", "text/x-sh", ["sh", "bash", "zsh", "fish"]],
  ["text", "text/x-sql", ["sql"]],
  ["text", "text/plain", ["txt", "log", "csv", "tsv", "env", "ini", "cfg", "conf", "lock"]],
];

const BY_EXTENSION = new Map<string, { kind: FileKind; mime: string }>(
  TYPES.flatMap(([kind, mime, extensions]) =>
    extensions.map((extension) => [extension, { kind, mime }] as const),
  ),
);

/**
 * Extensionless files that are text — the dotfiles and the build files every
 * repository has. Without this a `Makefile` or a `.gitignore` opens as
 * "binary, open externally", which reads as a bug.
 */
const TEXT_BASENAMES = new Set([
  "makefile",
  "dockerfile",
  "license",
  "licence",
  "notice",
  "readme",
  "changelog",
  "authors",
  "contributing",
  "codeowners",
  "procfile",
  "gemfile",
  "rakefile",
  "brewfile",
  "justfile",
]);

/** Lowercase extension without the dot; `""` when the name has none. */
export function extensionOf(filePath: string): string {
  const extension = path.extname(filePath);
  return extension.startsWith(".") ? extension.slice(1).toLowerCase() : "";
}

/** Which renderer a path selects, and the media type that goes with it. */
export function detectType(filePath: string): { kind: FileKind; mime: string; extension: string } {
  const extension = extensionOf(filePath);
  const known = BY_EXTENSION.get(extension);
  if (known) {
    return { ...known, extension };
  }
  const base = path.basename(filePath).toLowerCase();
  // A dotfile's "extension" is its whole name (`.gitignore` -> `gitignore`),
  // which is why the extension lookup above misses them.
  if (base.startsWith(".") || TEXT_BASENAMES.has(base.split(".")[0] ?? base)) {
    return { kind: "text", mime: "text/plain", extension };
  }
  return { kind: "binary", mime: "application/octet-stream", extension };
}

/**
 * Does this buffer look like text?
 *
 * A NUL byte in the first few KB is the same heuristic `git diff` uses, and it
 * is the one that matters: it keeps a `.bin` with a text-ish extension from
 * being poured into Monaco.
 */
export function looksBinary(sample: Uint8Array): boolean {
  const limit = Math.min(sample.length, 8000);
  for (let index = 0; index < limit; index += 1) {
    if (sample[index] === 0) {
      return true;
    }
  }
  return false;
}

/* -------------------------------------------------------------------------- */
/* Listing                                                                     */
/* -------------------------------------------------------------------------- */

const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

/** Directories first, then case-insensitive natural order — Finder's order. */
export function sortEntries(entries: DirEntry[]): DirEntry[] {
  return entries.sort((left, right) => {
    if (left.kind !== right.kind) {
      return left.kind === "directory" ? -1 : 1;
    }
    return COLLATOR.compare(left.name, right.name);
  });
}

export type ListOptions = {
  /** Rules for the root; read from disk when omitted. */
  rules?: IgnoreRules;
  /** Show what the rules hide. The tree's "Show ignored" toggle. */
  includeIgnored?: boolean;
};

/**
 * One directory's children. `directory` is root-relative; `""` is the root.
 */
export async function listDirectory(
  root: string,
  directory: string,
  options: ListOptions = {},
): Promise<DirEntry[]> {
  const rules = options.rules ?? (await IgnoreRules.read(root));
  const absolute = await resolveInRoot(root, directory);
  const realRoot = await fs.realpath(root).catch(() => path.resolve(root));

  const dirents = await fs.readdir(absolute, { withFileTypes: true });
  const entries: DirEntry[] = [];

  for (const dirent of dirents) {
    const child = path.join(absolute, dirent.name);
    const relative = toRelative(realRoot, child);
    const symlink = dirent.isSymbolicLink();

    // A symlink's own stat says "symlink"; what the tree wants to show is what
    // it points at. A broken one is skipped rather than shown as a mystery.
    const stats = await fs.stat(child).catch(() => null);
    if (!stats) {
      continue;
    }
    const kind = stats.isDirectory() ? "directory" : "file";
    if (!options.includeIgnored && rules.ignores(relative, kind === "directory")) {
      continue;
    }
    if (!stats.isDirectory() && !stats.isFile()) {
      continue;
    }

    entries.push({
      path: relative,
      name: dirent.name,
      kind,
      size: stats.isDirectory() ? 0 : stats.size,
      modifiedAt: Math.round(stats.mtimeMs),
      symlink,
    });
  }

  return sortEntries(entries);
}

/**
 * Every path under `directory`, flat, for the tree's fuzzy filter.
 *
 * Bounded by `limit` because "filter files" in a big repository is a UI
 * affordance, not an index: thirty thousand paths make the filter slow and the
 * result useless. The bound is reported so the UI can say so.
 */
export async function listPaths(
  root: string,
  directory = "",
  options: ListOptions & { limit?: number } = {},
): Promise<{ paths: string[]; truncated: boolean }> {
  const limit = options.limit ?? 20_000;
  const rules = options.rules ?? (await IgnoreRules.read(root));
  const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
  const start = await resolveInRoot(root, directory);

  const paths: string[] = [];
  const queue: string[] = [start];
  let truncated = false;

  while (queue.length > 0 && !truncated) {
    const current = queue.shift() as string;
    const dirents = await fs.readdir(current, { withFileTypes: true }).catch(() => []);
    for (const dirent of dirents) {
      const child = path.join(current, dirent.name);
      const relative = toRelative(realRoot, child);
      // Symlinked directories are not descended into: a link back up the tree
      // is an infinite walk, and the honest fix is not to follow any of them.
      const isDirectory = dirent.isDirectory();
      if (rules.ignores(relative, isDirectory)) {
        continue;
      }
      if (isDirectory) {
        queue.push(child);
      } else if (dirent.isFile()) {
        if (paths.length >= limit) {
          truncated = true;
          break;
        }
        paths.push(relative);
      }
    }
  }

  paths.sort(COLLATOR.compare);
  return { paths, truncated };
}

/* -------------------------------------------------------------------------- */
/* Reading and writing                                                         */
/* -------------------------------------------------------------------------- */

/** Above this a file opens read-only with a notice instead of in the editor. */
export const MAX_TEXT_BYTES = 4 * 1024 * 1024;

export async function statFile(root: string, target: string): Promise<FileStat> {
  const absolute = await resolveInRoot(root, target);
  const stats = await fs.stat(absolute);
  const { kind, mime, extension } = detectType(absolute);
  return {
    path: toRelative(await fs.realpath(root).catch(() => root), absolute),
    name: path.basename(absolute),
    kind: stats.isDirectory() ? "directory" : "file",
    size: stats.size,
    modifiedAt: Math.round(stats.mtimeMs),
    fileKind: stats.isDirectory() ? "binary" : kind,
    mime,
    extension,
  };
}

export type TextFile = {
  path: string;
  content: string;
  /** Content hash, so a save can tell whether the file moved under it. */
  revision: string;
  modifiedAt: number;
  size: number;
  /** True when the file was cut at MAX_TEXT_BYTES — the editor goes read-only. */
  truncated: boolean;
};

/** A revision is the content's hash: cheap, and stable across a copy. */
export function revisionOf(content: string | Uint8Array): string {
  return createHash("sha1").update(content).digest("hex").slice(0, 16);
}

export async function readTextFile(root: string, target: string): Promise<TextFile> {
  const absolute = await resolveInRoot(root, target);
  const stats = await fs.stat(absolute);
  const buffer = await fs.readFile(absolute);
  const truncated = buffer.byteLength > MAX_TEXT_BYTES;
  const slice = truncated ? buffer.subarray(0, MAX_TEXT_BYTES) : buffer;
  if (looksBinary(slice)) {
    throw new FsError("that file is not text");
  }
  const content = slice.toString("utf8");
  return {
    path: toRelative(await fs.realpath(root).catch(() => root), absolute),
    content,
    revision: revisionOf(buffer),
    modifiedAt: Math.round(stats.mtimeMs),
    size: stats.size,
    truncated,
  };
}

/**
 * Write text back.
 *
 * `expectedRevision` is the optimistic lock: the editor sends the revision it
 * loaded, and a write whose revision no longer matches is refused rather than
 * silently overwriting whatever changed the file — an agent's edit, most
 * likely, since agents write into the same tree the user is editing.
 */
export async function writeTextFile(
  root: string,
  target: string,
  content: string,
  expectedRevision?: string,
): Promise<TextFile> {
  const absolute = await resolveInRoot(root, target);
  if (expectedRevision) {
    const current = await fs.readFile(absolute).catch(() => null);
    if (current && revisionOf(current) !== expectedRevision) {
      throw new FsError("the file changed on disk since it was opened");
    }
  }
  await fs.writeFile(absolute, content, "utf8");
  return readTextFile(root, target);
}

export type BinaryFile = {
  path: string;
  mime: string;
  size: number;
  /** `data:` URL. The renderer cannot read a path; it can render one of these. */
  dataUrl: string;
};

/** Above this a binary is not inlined — a 40 MB data URL is not a preview. */
export const MAX_BINARY_BYTES = 24 * 1024 * 1024;

export async function readBinaryFile(root: string, target: string): Promise<BinaryFile> {
  const absolute = await resolveInRoot(root, target);
  const stats = await fs.stat(absolute);
  if (stats.size > MAX_BINARY_BYTES) {
    throw new FsError("that file is too large to preview");
  }
  const buffer = await fs.readFile(absolute);
  const { mime } = detectType(absolute);
  return {
    path: toRelative(await fs.realpath(root).catch(() => root), absolute),
    mime,
    size: stats.size,
    dataUrl: `data:${mime};base64,${buffer.toString("base64")}`,
  };
}

/* -------------------------------------------------------------------------- */
/* Watching                                                                    */
/* -------------------------------------------------------------------------- */

export type FileChange = {
  path: string;
  kind: "added" | "changed" | "removed";
  directory: boolean;
};

type Watcher = {
  close: () => Promise<void>;
};

/**
 * One chokidar watcher per root, refcounted by the tabs that asked for it.
 *
 * Changes are batched: a `git checkout` or an agent's multi-file edit fires
 * hundreds of events in a few milliseconds, and a tree that re-renders per
 * event janks for a second. The window is short enough to feel immediate.
 */
const BATCH_MS = 80;

export class FileWatchers {
  private readonly watchers = new Map<string, { watcher: Watcher; refs: number }>();
  private readonly pending = new Map<string, Map<string, FileChange>>();
  private readonly timers = new Map<string, NodeJS.Timeout>();

  constructor(private readonly emit: (root: string, changes: FileChange[]) => void) {}

  async watch(root: string): Promise<void> {
    const existing = this.watchers.get(root);
    if (existing) {
      existing.refs += 1;
      return;
    }
    // Imported here rather than at module scope so this file stays loadable in
    // a plain Node test without pulling chokidar's fsevents binding in.
    const { watch } = await import("chokidar");
    const rules = await IgnoreRules.read(root);
    const realRoot = await fs.realpath(root).catch(() => path.resolve(root));

    const watcher = watch(realRoot, {
      ignoreInitial: true,
      followSymlinks: false,
      // A repository's own history churns constantly and is never shown.
      ignored: (target: string) => {
        const relative = toRelative(realRoot, target);
        return relative !== "" && rules.ignores(relative, false) && rules.ignores(relative, true);
      },
      awaitWriteFinish: { stabilityThreshold: 40, pollInterval: 20 },
    });

    const record = (kind: FileChange["kind"], directory: boolean) => (target: string) => {
      this.queue(root, {
        path: toRelative(realRoot, target),
        kind,
        directory,
      });
    };

    watcher
      .on("add", record("added", false))
      .on("change", record("changed", false))
      .on("unlink", record("removed", false))
      .on("addDir", record("added", true))
      .on("unlinkDir", record("removed", true))
      // A watcher that dies silently leaves a stale tree, which looks like a
      // bug in the tree. Say so instead.
      .on("error", (error: unknown) => console.error(`[explorer] watch ${root}`, error));

    this.watchers.set(root, { watcher, refs: 1 });
  }

  async unwatch(root: string): Promise<void> {
    const existing = this.watchers.get(root);
    if (!existing) {
      return;
    }
    existing.refs -= 1;
    if (existing.refs > 0) {
      return;
    }
    this.watchers.delete(root);
    this.clearTimer(root);
    this.pending.delete(root);
    await existing.watcher.close();
  }

  async closeAll(): Promise<void> {
    const roots = [...this.watchers.keys()];
    for (const root of roots) {
      const existing = this.watchers.get(root);
      this.watchers.delete(root);
      this.clearTimer(root);
      await existing?.watcher.close();
    }
    this.pending.clear();
  }

  private queue(root: string, change: FileChange) {
    let batch = this.pending.get(root);
    if (!batch) {
      batch = new Map();
      this.pending.set(root, batch);
    }
    // Last write wins per path: an add followed by a change in the same window
    // is one row for the tree either way.
    batch.set(change.path, change);
    if (this.timers.has(root)) {
      return;
    }
    this.timers.set(
      root,
      setTimeout(() => {
        this.timers.delete(root);
        const flushing = this.pending.get(root);
        this.pending.delete(root);
        if (flushing && flushing.size > 0) {
          this.emit(root, [...flushing.values()]);
        }
      }, BATCH_MS),
    );
  }

  private clearTimer(root: string) {
    const timer = this.timers.get(root);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(root);
    }
  }
}

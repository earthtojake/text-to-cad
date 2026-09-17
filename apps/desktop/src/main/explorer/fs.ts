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
import { watch as watchDirectory, type FSWatcher } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";


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
/* Background watcher exclusions                                               */
/* -------------------------------------------------------------------------- */

/**
 * Avoid recursively watching dependency caches and repository internals. These
 * names never filter directory listings or file search. An explicitly listed
 * directory also gets a direct watcher, so browsing inside one stays live.
 */
const WATCH_IGNORED_NAMES = new Set([
  ".git", ".hg", ".svn", ".DS_Store", "node_modules", "__pycache__", ".venv",
  ".mypy_cache", ".pytest_cache", ".ruff_cache", ".turbo", ".next", ".vite", ".gradle",
]);

function backgroundWatchIgnores(relative: string): boolean {
  return relative.split("/").some((segment) => WATCH_IGNORED_NAMES.has(segment));
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

/**
 * Every directory child, independent of Git ignores or renderer support.
 * `directory` is root-relative; `""` is the root.
 */
export async function listDirectory(
  root: string,
  directory: string,
): Promise<DirEntry[]> {
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
  options: { limit?: number } = {},
): Promise<{ paths: string[]; truncated: boolean }> {
  const limit = options.limit ?? 20_000;
  const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
  const start = await resolveInRoot(root, directory);

  const paths: string[] = [];
  const queue: string[] = [start];
  const deferred: string[] = [];
  let truncated = false;

  while ((queue.length > 0 || deferred.length > 0) && !truncated) {
    // Visit project content before dependency caches can consume the cap. Both
    // queues are searched; no file is excluded because of Git or its renderer.
    const current = (queue.length > 0 ? queue : deferred).shift() as string;
    const dirents = await fs.readdir(current, { withFileTypes: true }).catch(() => []);
    for (const dirent of dirents) {
      const child = path.join(current, dirent.name);
      const relative = toRelative(realRoot, child);
      // Symlinked directories are not descended into: a link back up the tree
      // is an infinite walk, and the honest fix is not to follow any of them.
      const isDirectory = dirent.isDirectory();
      if (isDirectory) {
        (backgroundWatchIgnores(relative) ? deferred : queue).push(child);
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

/**
 * What each of `targets` is under the root: a file, a directory, or nothing.
 *
 * One `stat` per path and one answer for all of them, for the transcript's
 * path links (`explorer.exists`): a message naming twenty files is one round
 * trip, not twenty. A path outside the root answers `null` like a missing
 * one — the caller is drawing links, and "not linkable" is the same answer
 * for both.
 */
export async function pathKinds(root: string, targets: readonly string[]): Promise<Record<string, PathKind>> {
  const answers: Record<string, PathKind> = {};
  await Promise.all(
    targets.map(async (target) => {
      try {
        const absolute = await resolveInRoot(root, target);
        const stats = await fs.stat(absolute);
        answers[target] = stats.isDirectory() ? "directory" : stats.isFile() ? "file" : null;
      } catch {
        answers[target] = null;
      }
    }),
  );
  return answers;
}

export type PathKind = "file" | "directory" | null;

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
/* Creating, renaming, duplicating                                             */
/* -------------------------------------------------------------------------- */

/**
 * The tree's own edits: what the context menu offers besides opening.
 *
 * Each one resolves its target against the root the way every read does, and
 * none of them ever produces a path outside it — a rename takes a *name*, not
 * a path, so `../` cannot be smuggled in through the field, and a duplicate
 * lands beside its source. Trashing is not here: `shell.trashItem` is
 * Electron's, and this module stays plain Node (`src/main/ipc/explorer.ts`
 * resolves the path through `resolveInRoot` and hands it over).
 */

/** A name the tree can create or rename to: one path segment, nothing hidden in it. */
export function assertEntryName(name: string): void {
  if (name === "" || name === "." || name === "..") {
    throw new FsError("that is not a name");
  }
  if (/[\\/]/.test(name)) {
    throw new FsError("a name cannot contain a slash");
  }
  if (name.includes("\0")) {
    throw new FsError("that is not a name");
  }
}

/** The root-relative path of a would-be child of `directory`. */
function childPath(directory: string, name: string): string {
  return directory === "" ? name : `${directory}/${name}`;
}

/**
 * The first free name in a directory, Finder's way: `part.step`, then
 * `part copy.step`, `part copy 2.step`, … The extension stays at the end,
 * where the OS reads it; a directory has no extension to keep.
 */
export async function uniqueName(
  absoluteDirectory: string,
  name: string,
  isDirectory: boolean,
  suffix = "copy",
): Promise<string> {
  const extension = isDirectory ? "" : path.extname(name);
  const stem = extension ? name.slice(0, -extension.length) : name;
  const taken = new Set(await fs.readdir(absoluteDirectory).catch(() => [] as string[]));
  if (!taken.has(name)) {
    return name;
  }
  for (let count = 1; ; count += 1) {
    const candidate = `${stem} ${suffix}${count > 1 ? ` ${count}` : ""}${extension}`;
    if (!taken.has(candidate)) {
      return candidate;
    }
  }
}

/**
 * A new, empty file. Refused rather than truncated when something is already
 * there: "New file" over an existing one is a bug in the caller, not a request
 * to empty it.
 */
export async function createFile(root: string, directory: string, name: string): Promise<{ path: string }> {
  assertEntryName(name);
  const parent = await resolveInRoot(root, directory);
  const absolute = path.join(parent, name);
  try {
    await fs.writeFile(absolute, "", { flag: "wx" });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EEXIST") {
      throw new FsError("something with that name is already there");
    }
    throw error;
  }
  return { path: childPath(toRelative(await fs.realpath(root).catch(() => root), parent), name) };
}

export async function createDirectory(root: string, directory: string, name: string): Promise<{ path: string }> {
  assertEntryName(name);
  const parent = await resolveInRoot(root, directory);
  const absolute = path.join(parent, name);
  if (await fs.lstat(absolute).catch(() => null)) {
    throw new FsError("something with that name is already there");
  }
  await fs.mkdir(absolute);
  return { path: childPath(toRelative(await fs.realpath(root).catch(() => root), parent), name) };
}

/**
 * Rename in place. The new name has to be a name — one segment — so the
 * entry stays in its directory; moving is a different verb with a different
 * UI. A rename onto an existing entry is refused rather than resolved by
 * `rename(2)`'s own rule, which on POSIX replaces the target silently.
 */
export async function renameEntry(root: string, target: string, name: string): Promise<{ path: string }> {
  assertEntryName(name);
  const absolute = await resolveInRoot(root, target);
  const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
  if (absolute === realRoot) {
    throw new FsError("the project itself cannot be renamed here");
  }
  const destination = path.join(path.dirname(absolute), name);
  if (destination === absolute) {
    return { path: toRelative(realRoot, absolute) };
  }
  // A case-only rename on a case-insensitive filesystem stats as "exists";
  // it is the one legitimate rename onto an existing name.
  const caseOnly = destination.toLowerCase() === absolute.toLowerCase();
  if (!caseOnly && (await fs.lstat(destination).catch(() => null))) {
    throw new FsError("something with that name is already there");
  }
  await fs.rename(absolute, destination);
  return { path: toRelative(realRoot, destination) };
}

/**
 * A copy beside the original, named Finder's way. Directories copy whole;
 * symlinks inside them are copied as links, not followed, because a link
 * pointing up the tree is otherwise a copy that never ends.
 */
export async function duplicateEntry(root: string, target: string): Promise<{ path: string }> {
  const absolute = await resolveInRoot(root, target);
  const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
  if (absolute === realRoot) {
    throw new FsError("the project itself cannot be duplicated here");
  }
  const stats = await fs.stat(absolute);
  const parent = path.dirname(absolute);
  const name = await uniqueName(parent, path.basename(absolute), stats.isDirectory());
  const destination = path.join(parent, name);
  if (stats.isDirectory()) {
    await fs.cp(absolute, destination, { recursive: true, verbatimSymlinks: true, errorOnExist: true, force: false });
  } else {
    await fs.copyFile(absolute, destination, fs.constants.COPYFILE_EXCL);
  }
  return { path: toRelative(realRoot, destination) };
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

type WatchedRoot = {
  watcher: Watcher | null;
  direct: Map<string, FSWatcher>;
  refs: number;
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
  private readonly watchers = new Map<string, WatchedRoot>();
  private readonly listedDirectories = new Map<string, Set<string>>();
  private readonly pending = new Map<string, Map<string, FileChange>>();
  private readonly timers = new Map<string, NodeJS.Timeout>();

  constructor(private readonly emit: (root: string, changes: FileChange[]) => void) {}

  async watch(root: string): Promise<void> {
    const existing = this.watchers.get(root);
    if (existing) {
      existing.refs += 1;
      return;
    }
    // Register the owner before async setup: a directory listing or a second
    // tab may arrive while chokidar is loading.
    const owner: WatchedRoot = { watcher: null, direct: new Map(), refs: 1 };
    this.watchers.set(root, owner);
    // Imported here rather than at module scope so this file stays loadable in
    // a plain Node test without pulling chokidar's fsevents binding in.
    const { watch } = await import("chokidar");
    const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
    if (this.watchers.get(root) !== owner) return;

    const watcher = watch(realRoot, {
      ignoreInitial: true,
      followSymlinks: false,
      // Git-ignored model outputs are ordinary visible files. Only costly
      // infrastructure directories are excluded from this recursive watcher.
      ignored: (target: string) => {
        const relative = toRelative(realRoot, target);
        return relative !== "" && backgroundWatchIgnores(relative);
      },
      awaitWriteFinish: { stabilityThreshold: 40, pollInterval: 20 },
    });

    const record = (kind: FileChange["kind"], directory: boolean) => (target: string) => {
      if (this.watchers.get(root) !== owner) return;
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

    owner.watcher = watcher;
    await Promise.all([...(this.listedDirectories.get(root) ?? [])].map((directory) =>
      this.watchListedDirectory(root, directory),
    ));
  }

  /** Keep every explicitly browsed directory live without walking its children. */
  async watchListedDirectory(root: string, directory: string): Promise<void> {
    const absolute = await resolveInRoot(root, directory);
    const realRoot = await fs.realpath(root).catch(() => path.resolve(root));
    const relative = toRelative(realRoot, absolute);
    let listed = this.listedDirectories.get(root);
    if (!listed) {
      listed = new Set();
      this.listedDirectories.set(root, listed);
    }
    listed.add(relative);
    const owner = this.watchers.get(root);
    if (!owner || owner.direct.has(relative)) return;

    try {
      const direct = watchDirectory(absolute, { recursive: false }, (_event, filename) => {
        if (this.watchers.get(root) !== owner) return;
        const child = filename ? path.join(absolute, filename.toString()) : absolute;
        void fs.stat(child).catch(() => null).then((stats) => {
          if (this.watchers.get(root) !== owner) return;
          this.queue(root, {
            path: toRelative(realRoot, child),
            kind: stats ? "changed" : "removed",
            directory: stats?.isDirectory() ?? false,
          });
        });
      });
      direct.on("error", (error: unknown) => console.error(`[explorer] watch ${absolute}`, error));
      owner.direct.set(relative, direct);
    } catch (error) {
      // A failed watch must not make the directory disappear from browsing.
      console.error(`[explorer] watch ${absolute}`, error);
    }
  }

  async unwatch(root: string): Promise<void> {
    const existing = this.watchers.get(root);
    if (!existing) {
      this.listedDirectories.delete(root);
      return;
    }
    existing.refs -= 1;
    if (existing.refs > 0) {
      return;
    }
    this.watchers.delete(root);
    this.listedDirectories.delete(root);
    this.clearTimer(root);
    this.pending.delete(root);
    for (const direct of existing.direct.values()) direct.close();
    await existing.watcher?.close();
  }

  async closeAll(): Promise<void> {
    const roots = [...this.watchers.keys()];
    for (const root of roots) {
      const existing = this.watchers.get(root);
      this.watchers.delete(root);
      this.clearTimer(root);
      for (const direct of existing?.direct.values() ?? []) direct.close();
      await existing?.watcher?.close();
    }
    this.listedDirectories.clear();
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

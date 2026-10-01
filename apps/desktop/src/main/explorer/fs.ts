/**
 * The filesystem behind the explorer's file tab: the tree, the reads and
 * writes, and the watching — one chokidar watcher per root (skipping
 * dependency caches and repository internals), plus a direct `fs.watch` on
 * each directory the tree listed and on each opened file's parent, all
 * refcounted by the leases each page takes (`src/main/ipc/explorer.ts`).
 * Each opened file is also held per path with its inode, so a removal and an
 * addition of the same inode leave as one `moved` change (an agent's `mv`),
 * and an opened link is an alias that repeats its target's changes under its
 * own name (`FileWatchers`).
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
 * `listPaths`, the tree's flat fuzzy index, is the one recursive listing, bounded
 * by a path limit and reading a few directories ahead of the one it is on.
 *
 * Electron is deliberately not imported: this module is plain Node, so
 * `tests/unit/main/explorer-fs.test.ts` can run it.
 */
import { createHash, randomUUID } from "node:crypto";
import { statSync, watch as watchDirectory, type Dirent, type FSWatcher, type Stats } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import ignore from "ignore";

import { realDirectory } from "../projects/workspace";
import { startTimer } from "../timer";

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

/** Git exclusions bound background work only; browse and search never use them. */
async function readBackgroundWatchExclusions(root: string) {
  const sources = await Promise.all([
    fs.readFile(path.join(root, ".gitignore"), "utf8").catch(() => ""),
    fs.readFile(path.join(root, ".git", "info", "exclude"), "utf8").catch(() => ""),
  ]);
  const matcher = ignore().add(sources.flatMap((source) => source.split(/\r?\n/)));
  return (relative: string, stats?: Stats): boolean => {
    if (relative === "" || relative === ".") return false;
    if (backgroundWatchIgnores(relative)) return true;
    if (stats) return matcher.ignores(stats.isDirectory() ? `${relative}/` : relative);
    // Chokidar first probes without a stat. Directory-only rules must wait
    // for its typed probe, so a same-named ordinary file remains watchable.
    return matcher.ignores(relative) && matcher.ignores(`${relative}/`);
  };
}

/* -------------------------------------------------------------------------- */
/* Containment                                                                 */
/* -------------------------------------------------------------------------- */

export class FsError extends Error {
  override readonly name: string = "FsError";
  constructor(message: string, readonly code: "denied" | "not-found" | "already-exists" | "unsupported" | "conflict" | "error" = "error") { super(message); }
}
export class FsConflictError extends FsError {
  override readonly name = "FsConflictError";
  constructor(readonly actualRevision?: string) { super("the file changed on disk since it was opened", "conflict"); }
}

/** POSIX-separated, root-relative form of an absolute path. */
export function toRelative(root: string, target: string): string {
  const relative = path.relative(root, target);
  return relative === "" ? "" : relative.split(path.sep).join("/");
}

/**
 * True when a `path.relative` result leaves its base: ".." alone, ".." plus a
 * separator, or an absolute path (another Windows drive). A first segment that
 * only STARTS with dots (`..keep`) is an ordinary name and does not climb.
 */
export function climbsOut(relative: string): boolean {
  return relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative);
}

/** True when `target` is `root` or lives under it. */
export function isInside(root: string, target: string): boolean {
  if (target === root) {
    return true;
  }
  const relative = path.relative(root, target);
  return relative !== "" && !climbsOut(relative);
}

/** The root as the disk spells it, or as given (made absolute) when it cannot be read. */
const realRootOf = (root: string): Promise<string> => fs.realpath(root).catch(() => path.resolve(root));

/**
 * Resolve a renderer-supplied path against a root and refuse anything outside.
 *
 * Both halves are resolved with `realpath`, so a symlink in the root that
 * points at `/etc` is caught. A path that does not exist yet (a write to a new
 * file) is resolved through its deepest existing ancestor (`realDirectory`,
 * the ACP client's `confineToCwd` rule) with the missing tail kept as spelled:
 * `docs -> ~/.ssh` cannot carry a new `docs/authorized_keys` out of the root.
 *
 * The leaf is followed. That is right for reading and writing a file's
 * contents; a verb that acts on the row itself — trash, rename, duplicate —
 * wants `resolveEntryInRoot`.
 */
export async function resolveInRoot(root: string, target: string): Promise<string> {
  const realRoot = await realRootOf(root);
  const absolute = path.isAbsolute(target) ? target : path.join(realRoot, target);
  const resolved = await fs.realpath(absolute).catch(() => realDirectory(absolute));
  if (!isInside(realRoot, resolved)) {
    throw new FsError("path is outside the project", "denied");
  }
  return resolved;
}

/**
 * The entry a path names, NOT followed: its parent is resolved as
 * `resolveInRoot` would and has to be inside the root, and the last segment is
 * joined on as spelled. A symlink row is the link — trashing `current.step ->
 * v3.step` trashes the link, and a link pointing outside the root is still a
 * row inside it that can be trashed or renamed. The root itself answers as
 * the real root; callers refuse it by comparison.
 */
export async function resolveEntryInRoot(root: string, target: string): Promise<string> {
  const realRoot = await realRootOf(root);
  const absolute = path.resolve(realRoot, target);
  const spelledParent = path.dirname(absolute);
  const parent = await fs.realpath(spelledParent).catch(() => realDirectory(spelledParent));
  const entry = spelledParent === absolute ? parent : path.join(parent, path.basename(absolute));
  if (entry !== realRoot && !isInside(realRoot, parent)) {
    throw new FsError("path is outside the project", "denied");
  }
  return entry;
}

/**
 * The row a verb acts on: the entry itself (`resolveEntryInRoot`), its
 * root-relative path, and whether the tree shows it as a directory — a link to
 * a folder is one there, since its children are listed under it.
 */
export async function statEntry(root: string, target: string): Promise<{ absolute: string; path: string; directory: boolean; symlink: boolean }> {
  const absolute = await resolveEntryInRoot(root, target);
  const own = await fs.lstat(absolute);
  const followed = own.isSymbolicLink() ? await fs.stat(absolute).catch(() => own) : own;
  return {
    absolute,
    path: toRelative(await realRootOf(root), absolute),
    directory: followed.isDirectory(),
    symlink: own.isSymbolicLink(),
  };
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

/** Entries `listDirectory` stats at once. */
const LIST_STAT_BATCH = 64;

/**
 * Every directory child, independent of Git ignores or renderer support.
 * `directory` is root-relative; `""` is the root.
 */
export async function listDirectory(
  root: string,
  directory: string,
): Promise<DirEntry[]> {
  const absolute = await resolveInRoot(root, directory);
  const realRoot = await realRootOf(root);

  const dirents = await fs.readdir(absolute, { withFileTypes: true });
  const entries: DirEntry[] = [];

  // Every row needs its size and mtime, which the dirent does not carry, so
  // each is stat'ed; a folder of twenty thousand frames is twenty thousand
  // round trips, so they go a batch at a time rather than one after another.
  for (let from = 0; from < dirents.length; from += LIST_STAT_BATCH) {
    const rows = await Promise.all(dirents.slice(from, from + LIST_STAT_BATCH).map(async (dirent): Promise<DirEntry | null> => {
      const child = path.join(absolute, dirent.name);
      // A symlink's own stat says "symlink"; what the tree wants to show is what
      // it points at. A broken one is skipped rather than shown as a mystery.
      const stats = await fs.stat(child).catch(() => null);
      if (!stats || (!stats.isDirectory() && !stats.isFile())) {
        return null;
      }
      return {
        path: toRelative(realRoot, child),
        name: dirent.name,
        kind: stats.isDirectory() ? "directory" : "file",
        size: stats.isDirectory() ? 0 : stats.size,
        modifiedAt: Math.round(stats.mtimeMs),
        symlink: dirent.isSymbolicLink(),
      };
    }));
    for (const row of rows) if (row) entries.push(row);
  }

  return sortEntries(entries);
}

/** Directories `listPaths` reads ahead of the one it is on. */
const LIST_READ_AHEAD = 16;

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
  const realRoot = await realRootOf(root);
  const start = await resolveInRoot(root, directory);

  const paths: string[] = [];
  const queue: string[] = [start];
  const deferred: string[] = [];
  let truncated = false;

  // Breadth-first, and consumed strictly in the order the directories were
  // found, so a capped walk returns the same paths it did when it read one
  // directory at a time. What changed is that the next `LIST_READ_AHEAD`
  // directories are already being read while this one is taken apart: one
  // `readdir` per await made a 5,000-path project a ~700 ms wait on the disk's
  // latency, not its throughput. A list is walked by index — `shift()` on a
  // queue this long is itself quadratic.
  const drain = async (list: string[]) => {
    const reads = new Map<number, Promise<Dirent[]>>();
    for (let next = 0; next < list.length && !truncated; next += 1) {
      for (let ahead = next; ahead < Math.min(list.length, next + LIST_READ_AHEAD); ahead += 1) {
        if (!reads.has(ahead)) {
          reads.set(ahead, fs.readdir(list[ahead] as string, { withFileTypes: true }).catch(() => []));
        }
      }
      const current = list[next] as string;
      const dirents = await (reads.get(next) as Promise<Dirent[]>);
      reads.delete(next);
      // A directory's links are stat'ed together: one `stat` per await was the same wait on the
      // disk's latency that the read-ahead removed for `readdir`.
      const linked = new Map<string, boolean>(
        await Promise.all(
          dirents
            .filter((dirent) => dirent.isSymbolicLink())
            .map(async (dirent) => [
              dirent.name,
              Boolean((await fs.stat(path.join(current, dirent.name)).catch(() => null))?.isFile()),
            ] as const),
        ),
      );
      for (const dirent of dirents) {
        const child = path.join(current, dirent.name);
        const relative = toRelative(realRoot, child);
        // Symlinked directories are not descended into: a link back up the tree
        // is an infinite walk, and the honest fix is not to follow any of them.
        const isDirectory = dirent.isDirectory();
        if (isDirectory) {
          (backgroundWatchIgnores(relative) ? deferred : queue).push(child);
        } else if (dirent.isFile() || linked.get(dirent.name)) {
          // A link to a file is a row in the tree (`listDirectory` reads what it points at), so
          // it is in the filter's index too. A broken one is neither.
          if (paths.length >= limit) {
            truncated = true;
            break;
          }
          paths.push(relative);
        }
      }
    }
  };

  // Visit project content before dependency caches can consume the cap. Both
  // lists are searched; no file is excluded because of Git or its renderer.
  // Nothing under a deferred directory is ever ordinary again (its path keeps
  // the ignored segment), so the second pass only grows `deferred`.
  await drain(queue);
  await drain(deferred);

  paths.sort(COLLATOR.compare);
  return { paths, truncated };
}

/* -------------------------------------------------------------------------- */
/* Reading and writing                                                         */
/* -------------------------------------------------------------------------- */

/** Above this a file opens read-only with a notice instead of in the editor. */
export const MAX_TEXT_BYTES = 4 * 1024 * 1024;

/**
 * A file as a tab opens it. The path is the one asked for, not its target:
 * a tab opened on `current.step -> v3.step` is the link, so its crumbs, its
 * identity and the changes it listens for stay the link's (`FileWatchers`
 * reports its target's changes under the link's name too). The type, size
 * and time are the target's.
 */
export async function statFile(root: string, target: string): Promise<FileStat> {
  const absolute = await resolveInRoot(root, target);
  const stats = await fs.stat(absolute);
  const { kind, mime, extension } = detectType(absolute);
  const realRoot = await realRootOf(root);
  const spelled = path.resolve(realRoot, target);
  const identity = isInside(realRoot, spelled) ? spelled : absolute;
  return {
    path: toRelative(realRoot, identity),
    name: path.basename(identity),
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
  /**
   * True when the bytes are not UTF-8 (a Latin-1 or Shift-JIS file). They are
   * shown with U+FFFD where a byte did not decode, and a save would write
   * those replacement characters over the original bytes — so it is shown,
   * not edited.
   */
  readOnly?: boolean;
};

/** A revision is the content's hash: cheap, and stable across a copy. */
export function revisionOf(content: string | Uint8Array): string {
  return createHash("sha1").update(content).digest("hex").slice(0, 16);
}

export async function readTextFile(root: string, target: string): Promise<TextFile> {
  const absolute = await resolveInRoot(root, target);
  // Only the cap and one byte more are read: a 50 MB log is not read and
  // hashed whole to show its first 4 MB, and a file over 2 GiB is not a
  // readFile error (ERR_FS_FILE_TOO_LARGE) instead of a truncated view.
  const handle = await fs.open(absolute, "r");
  let stats: Stats;
  let slice: Buffer;
  let truncated: boolean;
  try {
    stats = await handle.stat();
    const buffer = Buffer.alloc(Math.min(stats.size, MAX_TEXT_BYTES) + 1);
    let filled = 0;
    while (filled < buffer.byteLength) {
      const { bytesRead } = await handle.read(buffer, filled, buffer.byteLength - filled, filled);
      if (bytesRead === 0) break;
      filled += bytesRead;
    }
    truncated = filled > MAX_TEXT_BYTES;
    slice = buffer.subarray(0, Math.min(filled, MAX_TEXT_BYTES));
  } finally { await handle.close(); }
  if (looksBinary(slice)) {
    throw new FsError("that file is not text", "unsupported");
  }
  const content = slice.toString("utf8");
  return {
    path: toRelative(await realRootOf(root), absolute),
    content,
    // A truncated file is read-only and never saved back, so its revision
    // need not be the whole file's hash — only change when the file does.
    revision: truncated ? revisionOf(`${revisionOf(slice)}:${stats.size}:${stats.mtimeMs}`) : revisionOf(slice),
    modifiedAt: Math.round(stats.mtimeMs),
    size: stats.size,
    truncated,
    ...(isUtf8(slice, truncated) ? {} : { readOnly: true }),
  };
}

/** A cut may split the last character: only bytes before it have to decode. */
function isUtf8(bytes: Uint8Array, truncated: boolean): boolean {
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(bytes, { stream: truncated });
    return true;
  } catch {
    return false;
  }
}

/**
 * Write text back.
 *
 * `expectedRevision` is the optimistic lock: the editor sends the revision it
 * loaded, and a write whose revision no longer matches is refused rather than
 * silently overwriting whatever changed the file — an agent's edit, most
 * likely, since agents write into the same tree the user is editing.
 */
const textWrites = new Map<string, Promise<TextFile>>();
export async function writeTextFile(
  root: string,
  target: string,
  content: string,
  expectedRevision?: string,
): Promise<TextFile> {
  const absolute = await resolveInRoot(root, target);
  // Serialize this process's writers so two editors cannot both accept the same
  // revision. External writes are checked immediately before the atomic rename.
  const work = (textWrites.get(absolute)?.catch(() => undefined) ?? Promise.resolve()).then(async () => {
    const temporary = path.join(path.dirname(absolute), `.${path.basename(absolute)}.text-to-cad-${randomUUID()}.tmp`);
    const buffer = Buffer.from(content, "utf8");
    let created = false;
    const checkRevision = async () => {
      if (expectedRevision === undefined) return;
      const current = await fs.readFile(absolute).catch((error: NodeJS.ErrnoException) => {
        if (error.code === "ENOENT") return null;
        throw error;
      });
      const actual = current === null ? undefined : revisionOf(current);
      if (actual !== expectedRevision) throw new FsConflictError(actual);
    };
    try {
      await checkRevision();
      const mode = await fs.stat(absolute).then(stat => stat.mode & 0o777).catch((error: NodeJS.ErrnoException) => {
        if (error.code === "ENOENT") return null;
        throw error;
      });
      const handle = await fs.open(temporary, "wx", mode ?? 0o666);
      created = true;
      let modifiedAt: number;
      try {
        // open's mode is filtered by umask; an existing file keeps its exact
        // permissions, while a new file still uses normal process defaults.
        if (mode !== null) await handle.chmod(mode);
        await handle.writeFile(buffer);
        await handle.sync();
        modifiedAt = Math.round((await handle.stat()).mtimeMs);
      } finally { await handle.close(); }
      const relative = toRelative(await fs.realpath(root), absolute);
      if (await resolveInRoot(root, target) !== absolute) throw new FsError("the file's location changed while saving");
      await checkRevision();
      await fs.rename(temporary, absolute);
      created = false;
      // Nothing fallible follows the commit: an external delete/rename must
      // not turn successfully written bytes into a reported failed save.
      return { path: relative, content, revision: revisionOf(buffer), modifiedAt, size: buffer.byteLength, truncated: false };
    } finally { if (created) await fs.unlink(temporary).catch(() => {}); }
  });
  textWrites.set(absolute, work);
  try { return await work; } finally { if (textWrites.get(absolute) === work) textWrites.delete(absolute); }
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
    path: toRelative(await realRootOf(root), absolute),
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
 * resolves the entry through `resolveEntryInRoot` and hands it over).
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
      throw new FsError("something with that name is already there", "already-exists");
    }
    throw error;
  }
  return { path: childPath(toRelative(await realRootOf(root), parent), name) };
}

export async function createDirectory(root: string, directory: string, name: string): Promise<{ path: string }> {
  assertEntryName(name);
  const parent = await resolveInRoot(root, directory);
  const absolute = path.join(parent, name);
  if (await fs.lstat(absolute).catch(() => null)) {
    throw new FsError("something with that name is already there", "already-exists");
  }
  await fs.mkdir(absolute);
  return { path: childPath(toRelative(await realRootOf(root), parent), name) };
}

/**
 * Rename in place. The new name has to be a name — one segment — so the
 * entry stays in its directory; moving is a different verb with a different
 * UI. A rename onto an existing entry is refused rather than resolved by
 * `rename(2)`'s own rule, which on POSIX replaces the target silently.
 */
export async function renameEntry(root: string, target: string, name: string): Promise<{ path: string }> {
  assertEntryName(name);
  const absolute = await resolveEntryInRoot(root, target);
  const realRoot = await realRootOf(root);
  if (absolute === realRoot) {
    throw new FsError("the project itself cannot be renamed here");
  }
  const source = await fs.lstat(absolute);
  const destination = path.join(path.dirname(absolute), name);
  if (destination === absolute) {
    return { path: toRelative(realRoot, absolute) };
  }
  // A case-only rename on a case-insensitive filesystem stats as "exists":
  // the same entry, and the one legitimate rename onto an existing name. On a
  // case-sensitive disk `A.txt` beside `a.txt` is a different file, and
  // rename(2) would replace it — so the two have to be the same inode.
  const existing = await fs.lstat(destination).catch(() => null);
  if (existing) {
    const caseOnly = destination.toLowerCase() === absolute.toLowerCase();
    if (!caseOnly || existing.dev !== source.dev || existing.ino !== source.ino) {
      throw new FsError("something with that name is already there", "already-exists");
    }
  }
  await fs.rename(absolute, destination);
  return { path: toRelative(realRoot, destination) };
}

/**
 * A copy beside the original, named Finder's way. Directories copy whole. A
 * symlink row, and the symlinks inside a directory, are copied as links, not
 * followed: a link pointing up the tree is otherwise a copy that never ends,
 * and one pointing outside would copy what is outside into the project.
 */
export async function duplicateEntry(root: string, target: string): Promise<{ path: string }> {
  const absolute = await resolveEntryInRoot(root, target);
  const realRoot = await realRootOf(root);
  if (absolute === realRoot) {
    throw new FsError("the project itself cannot be duplicated here");
  }
  const stats = await fs.lstat(absolute);
  const parent = path.dirname(absolute);
  const name = await uniqueName(parent, path.basename(absolute), stats.isDirectory());
  const destination = path.join(parent, name);
  if (stats.isSymbolicLink()) {
    // A link row duplicates as a link, the way links inside a folder do.
    await fs.symlink(await fs.readlink(absolute), destination);
  } else if (stats.isDirectory()) {
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
  kind: "moved";
  path: string;
  previousPath: string;
  directory: boolean;
} | {
  path: string;
  kind: "added" | "changed" | "removed";
  directory: boolean;
  /**
   * The changed file's content revision, as `readTextFile` would report it.
   * An editor compares it with the revision it holds, so the echo of its own
   * save is not mistaken for someone else's edit.
   */
  revision?: string;
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
 * One chokidar watcher per root, refcounted by the page leases that asked
 * for it, and beside it a direct `fs.watch` per listed directory and per
 * opened file's parent (`watchListedDirectory`), so a directory the
 * background watcher skips stays live while it is on screen.
 *
 * Opened files are held per path (`holds`) with their inode (`identities`).
 * A batch that removes one waits `MOVE_WAIT_MS` for the addition, and a
 * removal and an arrival with the same inode leave as one `moved` change
 * (`pairMoves`), the holds moving with it. An opened link is an alias
 * (`aliases`): its target's changes are repeated under its name, and its own
 * inode is its identity; when `ln -sfn` re-points it, the inode is taken
 * again and the alias follows the new target (`retarget`). A
 * release that overtakes the watch it follows is counted (`arriving`,
 * `owed`) and given back once that watch holds.
 *
 * Changes are batched: a `git checkout` or an agent's multi-file edit fires
 * hundreds of events in a few milliseconds, and a tree that re-renders per
 * event janks for a second. The window is short enough to feel immediate.
 */
const BATCH_MS = 80;
/**
 * How long a batch that removed an open file waits for the name it went to.
 * A rename is an unlink and an add to chokidar, and the add is held back by
 * `awaitWriteFinish` until the file's size has settled.
 */
const MOVE_WAIT_MS = 250;

/** A file's inode; for an opened link (`link`), the link's own, which its target's writes never change. */
type Identity = { dev: number; ino: number; link?: true };

/**
 * When a batch leaves: `run` after `ms`, and the function that cancels it.
 * A timer by default; a test hands in its own clock, so a window is a thing
 * it steps through rather than sleeps against.
 */
export type Schedule = (run: () => void, ms: number) => () => void;

const timer: Schedule = (run, ms) => startTimer(ms, run);

export class FileWatchers {
  private readonly watchers = new Map<string, WatchedRoot>();
  private readonly listedDirectories = new Map<string, Set<string>>();
  private readonly pending = new Map<string, Map<string, FileChange>>();
  private readonly timers = new Map<string, () => void>();
  /** Each root's batches leave in order, however long one takes to settle. */
  private readonly flushes = new Map<string, Promise<void>>();
  /**
   * The inode of each file a tab has open, by root and path. The watcher
   * reports an agent's `mv` or `git mv` as a removal and an addition; the
   * inode is what says the two are one file, so a tab can follow it. It is
   * taken again whenever the file changes under its own name — the app's
   * own save is an atomic rename, a new inode at the same path — and
   * forgotten when the last tab holding the path lets it go (`unwatch`).
   */
  private readonly identities = new Map<string, Map<string, Identity>>();
  /** Per root, each opened link's target and the link paths tabs hold for it. */
  private readonly aliases = new Map<string, Map<string, Set<string>>>();
  /** Per root, how many opens (`watchEntry`) each path has not yet given back. */
  private readonly holds = new Map<string, Map<string, number>>();
  /**
   * Per root, the paths a `watch` is still on its way to hold again, and the
   * releases that arrived for them first. A tab that remounts and closes at
   * once sends its unwatch behind its watch, but the watch awaits the root
   * before it holds: a release that found no hold would be dropped, and the
   * hold taken after it never given back.
   */
  private readonly arriving = new Map<string, Map<string, number>>();
  private readonly owed = new Map<string, Map<string, number>>();

  constructor(
    private readonly emit: (root: string, changes: FileChange[]) => void,
    private readonly schedule: Schedule = timer,
  ) {}

  /**
   * Take one watch of the root. `paths` are files a tab opened and gave back
   * with an earlier `unwatch` while it stayed open (a remount): held again,
   * each as its open stat held it.
   */
  async watch(root: string, paths: readonly string[] = []): Promise<void> {
    for (const relative of paths) count(this.arriving, root, relative, 1);
    try {
      await this.watchRoot(root);
    } catch (error) {
      for (const relative of paths) count(this.arriving, root, relative, -1);
      throw error;
    }
    for (const relative of paths) {
      await this.watchEntry(root, { path: relative, kind: "file" }).catch(() => {});
      count(this.arriving, root, relative, -1);
      // Released while it was on its way: given back now that it is held.
      if ((this.owed.get(root)?.get(relative) ?? 0) > 0) {
        count(this.owed, root, relative, -1);
        this.release(root, [relative]);
      }
    }
  }

  private async watchRoot(root: string): Promise<void> {
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
    const realRoot = await realRootOf(root);
    const ignoredInBackground = await readBackgroundWatchExclusions(realRoot);
    if (this.watchers.get(root) !== owner) return;

    const watcher = watch(realRoot, {
      ignoreInitial: true,
      followSymlinks: false,
      // Runtime bundles and generated trees can contain hundreds of thousands
      // of files. Visible/opened directories get separate direct watches below.
      ignored: (target: string, stats?: Stats) => {
        const relative = toRelative(realRoot, target);
        return ignoredInBackground(relative, stats);
      },
      awaitWriteFinish: { stabilityThreshold: 40, pollInterval: 20 },
    });

    const record = (kind: "added" | "changed" | "removed", directory: boolean) => (target: string) => {
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

  /** An opened file stays live even when its parent has never been expanded. */
  async watchEntry(root: string, entry: Pick<FileStat, "path" | "kind">): Promise<void> {
    await this.watchListedDirectory(root, entry.kind === "directory" ? entry.path : path.posix.dirname(entry.path));
    if (entry.kind !== "file") return;
    const realRoot = await realRootOf(root);
    const real = toRelative(realRoot, await resolveInRoot(root, entry.path));
    if (real !== entry.path) {
      // A link, or a path through a linked directory. Events name the target
      // (symlinks are not followed), so the target's directory is watched
      // and its changes are repeated under the name the tab holds.
      await this.watchListedDirectory(root, path.posix.dirname(real));
      if (!this.watchers.has(root)) return;
      const links = inner(this.aliases, root);
      links.set(real, new Set([...(links.get(real) ?? []), entry.path]));
      this.hold(root, entry.path);
      // The inode is the target's: a move of the target is not a move of
      // the link, which is left dangling. A link itself renamed is its tab's
      // file moved, though, so the link's own inode is its identity
      // (`pairMoves`) — a path through a linked directory has none.
      const own = await fs.lstat(path.join(realRoot, entry.path)).catch(() => null);
      if (own?.isSymbolicLink() && this.watchers.has(root)) {
        const known = inner(this.identities, root);
        known.set(entry.path, { dev: own.dev, ino: own.ino, link: true });
      }
      return;
    }
    const stats = await fs.stat(path.join(realRoot, entry.path)).catch(() => null);
    if (!stats || !this.watchers.has(root)) return;
    const known = inner(this.identities, root);
    known.set(entry.path, { dev: stats.dev, ino: stats.ino });
    this.hold(root, entry.path);
  }

  /**
   * Take an open file's inode again after the app wrote it. A save is an
   * atomic rename, so the file at the path is a new inode; its echo may be
   * batched long after, and an agent's `mv` before then would not be
   * recognised as the same file.
   */
  async refreshEntry(root: string, relative: string): Promise<void> {
    const known = this.identities.get(root);
    if (!known?.has(relative) || known.get(relative)?.link) return;
    const realRoot = await realRootOf(root);
    const stats = await fs.stat(path.join(realRoot, relative)).catch(() => null);
    if (stats?.isFile() && known.has(relative)) known.set(relative, { dev: stats.dev, ino: stats.ino });
  }

  private hold(root: string, relative: string) {
    const held = inner(this.holds, root);
    held.set(relative, (held.get(relative) ?? 0) + 1);
  }

  /** A closed tab's paths: at the last hold, its inode and its link are forgotten. */
  private release(root: string, paths: readonly string[]) {
    const held = this.holds.get(root);
    for (const relative of paths) {
      const holding = held?.get(relative) ?? 0;
      if (holding === 0) {
        if ((this.arriving.get(root)?.get(relative) ?? 0) > 0) count(this.owed, root, relative, 1);
        continue;
      }
      if (holding > 1) {
        held!.set(relative, holding - 1);
        continue;
      }
      held!.delete(relative);
      this.identities.get(root)?.delete(relative);
      const links = this.aliases.get(root);
      for (const [target, names] of links ?? []) {
        names.delete(relative);
        if (names.size === 0) links!.delete(target);
      }
    }
  }

  /** Keep every explicitly browsed directory live without walking its children. */
  async watchListedDirectory(root: string, directory: string): Promise<void> {
    const absolute = await resolveInRoot(root, directory);
    const realRoot = await realRootOf(root);
    const relative = toRelative(realRoot, absolute);
    let listed = this.listedDirectories.get(root);
    if (!listed) {
      listed = new Set();
      this.listedDirectories.set(root, listed);
    }
    listed.add(relative);
    const owner = this.watchers.get(root);
    if (!owner || owner.direct.has(relative)) return;

    // A watch is on the directory's inode: once `rm -rf` takes the directory
    // it hears nothing, including the directory made again under its name.
    // It is closed and forgotten here, and armed afresh when a change names
    // the directory again (`queue`) or the tree lists it again.
    const disarm = (direct: FSWatcher) => {
      if (owner.direct.get(relative) !== direct) return;
      owner.direct.delete(relative);
      direct.close();
    };
    // Taken without yielding, so a second listing cannot arm the same directory meanwhile.
    const armed = statSync(absolute, { throwIfNoEntry: false });
    try {
      const direct: FSWatcher = watchDirectory(absolute, { recursive: false }, (_event, filename) => {
        if (this.watchers.get(root) !== owner) return;
        const child = filename ? path.join(absolute, filename.toString()) : absolute;
        void fs.stat(child).catch(() => null).then(async (stats) => {
          if (this.watchers.get(root) !== owner) return;
          if (!stats) {
            // The watch's own directory went (its event names the directory
            // itself, which no child of it is). Made again already, as with
            // `rm -rf out && mkdir out`, the name stats but is another inode:
            // the dead watch is let go all the same, and the directory is
            // reported changed rather than a child that never was removed —
            // which lists it again and so arms it again (`queue`).
            const now = await fs.stat(absolute).catch(() => null);
            if (!now || (filename?.toString() === path.basename(absolute) && (now.ino !== armed?.ino || now.dev !== armed?.dev))) {
              disarm(direct);
              if (now) this.queue(root, { path: relative, kind: "changed", directory: true });
              return;
            }
          }
          this.queue(root, {
            path: toRelative(realRoot, child),
            kind: stats ? "changed" : "removed",
            directory: stats?.isDirectory() ?? false,
          });
        });
      });
      direct.on("error", (error: unknown) => {
        console.error(`[explorer] watch ${absolute}`, error);
        disarm(direct);
      });
      owner.direct.set(relative, direct);
    } catch (error) {
      // A failed watch must not make the directory disappear from browsing.
      console.error(`[explorer] watch ${absolute}`, error);
    }
  }

  /**
   * Give back one watch of the root and, with it, the paths the leaving tab
   * opened (one per `watchEntry` it caused).
   */
  async unwatch(root: string, paths: readonly string[] = []): Promise<void> {
    this.release(root, paths);
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
    this.identities.delete(root);
    this.aliases.delete(root);
    this.holds.delete(root);
    this.owed.delete(root);
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
    this.identities.clear();
    this.aliases.clear();
    this.holds.clear();
    this.owed.clear();
    this.pending.clear();
  }

  private queue(root: string, change: FileChange) {
    const batch = inner(this.pending, root);
    // Last write wins per path: an add followed by a change in the same window
    // is one row for the tree either way.
    batch.set(change.path, change);
    if (change.directory && change.kind !== "removed" && this.listedDirectories.get(root)?.has(change.path)
      && !this.watchers.get(root)?.direct.has(change.path)) {
      void this.watchListedDirectory(root, change.path).catch(() => {});
    }
    const moving = change.kind === "removed" && !change.directory && this.identities.get(root)?.has(change.path);
    if (this.timers.has(root)) {
      if (!moving) return;
      this.clearTimer(root);
    }
    this.timers.set(
      root,
      this.schedule(() => {
        this.timers.delete(root);
        const flushing = this.pending.get(root);
        this.pending.delete(root);
        if (!flushing || flushing.size === 0) return;
        const owner = this.watchers.get(root);
        const flushed = (this.flushes.get(root) ?? Promise.resolve())
          .then(() => this.settle(root, [...flushing.values()]))
          .then((changes) => {
            if (this.watchers.get(root) === owner) this.emit(root, changes);
          })
          .catch((error: unknown) => console.error(`[explorer] watch ${root}`, error))
          .finally(() => {
            if (this.flushes.get(root) === flushed) this.flushes.delete(root);
          });
        this.flushes.set(root, flushed);
      }, moving ? MOVE_WAIT_MS : BATCH_MS),
    );
  }

  /**
   * Stamp each changed file a tab has open with its content revision. A
   * save's own write comes back through the watcher a moment later; without
   * a revision the editor that saved cannot tell it from an agent's edit,
   * and a clean buffer reloads under the cursor while a dirty one is told
   * the file changed on disk. A file no tab holds has no editor to tell, so
   * it is not read: a checkout that touches five thousand files is five
   * thousand paths here, not five thousand reads on main's thread. A file
   * over the text cap opens read-only and is never saved from here, so it
   * is not read either.
   *
   * An open file that changed under its own name has its inode taken again
   * here: after an atomic save it is a different inode at the same path. An
   * open link's is the link's own, and its target is still what is read.
   */
  private async settle(root: string, changes: FileChange[]): Promise<FileChange[]> {
    const realRoot = await realRootOf(root);
    const known = this.identities.get(root);
    const links = this.aliases.get(root);
    const stamped = await Promise.all(changes.map(async (change) => {
      if ((change.kind !== "changed" && change.kind !== "added") || change.directory) return change;
      // A held path whose identity a removal dropped (a checkout away and
      // back) is taken again when it reappears.
      const retaken = change.kind === "added" && !known?.has(change.path) && this.holds.get(root)?.has(change.path);
      if (!known?.has(change.path) && !links?.has(change.path) && !retaken) return change;
      const absolute = path.join(realRoot, change.path);
      // A link's identity is its own inode, taken again when it is still a
      // link: `ln -sfn` re-points it as a new link under the same name, and
      // a later rename of that one is its tab's file moved. The new link may
      // name another target, whose changes are then the ones repeated.
      if (known?.get(change.path)?.link) {
        const own = await fs.lstat(absolute).catch(() => null);
        if (own?.isSymbolicLink() && known.get(change.path)?.link) {
          known.set(change.path, { dev: own.dev, ino: own.ino, link: true });
          await this.retarget(root, realRoot, change.path);
        }
      }
      const stats = await fs.stat(absolute).catch(() => null);
      if (!stats?.isFile()) return change;
      if (known?.has(change.path) && !known.get(change.path)?.link) known.set(change.path, { dev: stats.dev, ino: stats.ino });
      else if (retaken) this.identities.get(root)?.set(change.path, { dev: stats.dev, ino: stats.ino });
      if (change.kind !== "changed" || stats.size > MAX_TEXT_BYTES) return change;
      const content = await fs.readFile(absolute).catch(() => null);
      return content ? { ...change, revision: revisionOf(content) } : change;
    }));
    return this.throughLinks(root, await this.pairMoves(root, realRoot, stamped));
  }

  /**
   * An opened link's name moved to the target it points at now. Left under
   * the old one, `ln -sfn` would keep repeating a file the tab no longer
   * shows and never the one it does. A target outside the root, or none,
   * is no target: nothing is repeated for it.
   */
  private async retarget(root: string, realRoot: string, link: string): Promise<void> {
    const real = await resolveInRoot(root, link).then((absolute) => toRelative(realRoot, absolute), () => null);
    if (real !== null && real !== link) await this.watchListedDirectory(root, path.posix.dirname(real));
    const links = this.aliases.get(root);
    if (!links || !this.watchers.has(root)) return;
    for (const [target, names] of links) {
      if (target === real || !names.delete(link)) continue;
      if (names.size === 0) links.delete(target);
    }
    if (real !== null && real !== link) links.set(real, new Set([...(links.get(real) ?? []), link]));
  }

  /** Each change to an opened link's target, repeated under the link's name. */
  private throughLinks(root: string, changes: FileChange[]): FileChange[] {
    const links = this.aliases.get(root);
    if (!links?.size) return changes;
    const repeated = changes.flatMap((change) => {
      const target = change.kind === "moved" ? change.previousPath : change.path;
      const names = links.get(target);
      if (!names || change.directory) return [];
      // A target moved away leaves the link dangling: to its tab, a removal.
      return [...names].map((name): FileChange => change.kind === "moved"
        ? { kind: "removed", path: name, directory: false }
        : { ...change, path: name });
    });
    return repeated.length ? [...changes, ...repeated] : changes;
  }

  /**
   * An open file removed in the same batch as a file that appeared with its
   * inode was moved, not deleted: one `moved` replaces the pair, so its tab
   * takes the new name (and a dirty buffer can still be saved) instead of
   * showing "Could not open that file". A removal with no such partner stays
   * a removal.
   */
  private async pairMoves(root: string, realRoot: string, changes: FileChange[]): Promise<FileChange[]> {
    const known = this.identities.get(root);
    const removed = changes.filter((change) => change.kind === "removed" && !change.directory && known?.has(change.path));
    if (!known || removed.length === 0) return changes;
    const arrivals = changes.filter((change) => (change.kind === "added" || change.kind === "changed") && !change.directory);
    // The arrival's own inode: a link that arrives is matched by the link's, not its target's.
    const stats = await Promise.all(arrivals.map((change) => fs.lstat(path.join(realRoot, change.path)).catch(() => null)));
    const moves = new Map<FileChange, FileChange>();
    const taken = new Set<FileChange>();
    for (const removal of removed) {
      const identity = known.get(removal.path)!;
      const index = arrivals.findIndex((arrival, at) => !taken.has(arrival)
        && (identity.link ? stats[at]?.isSymbolicLink() : stats[at]?.isFile())
        && stats[at]!.ino === identity.ino && stats[at]!.dev === identity.dev);
      if (index < 0) {
        known.delete(removal.path);
        continue;
      }
      const arrival = arrivals[index]!;
      taken.add(arrival);
      moves.set(removal, { kind: "moved", previousPath: removal.path, path: arrival.path, directory: false });
      known.delete(removal.path);
      known.set(arrival.path, identity);
      // The tabs that held the old name hold the new one (the renderer
      // follows the move the same way, `fileSource.ts`).
      const held = this.holds.get(root);
      const count = held?.get(removal.path) ?? 0;
      if (held && count > 0) {
        held.delete(removal.path);
        held.set(arrival.path, (held.get(arrival.path) ?? 0) + count);
      }
      // A link's target is repeated under the name its tab holds now.
      for (const names of identity.link ? this.aliases.get(root)?.values() ?? [] : []) {
        if (names.delete(removal.path)) names.add(arrival.path);
      }
    }
    return changes.filter((change) => !taken.has(change)).map((change) => moves.get(change) ?? change);
  }

  private clearTimer(root: string) {
    const cancel = this.timers.get(root);
    if (cancel) {
      cancel();
      this.timers.delete(root);
    }
  }
}

/** The map a root keys in `outer`, made and stored there if it has none. */
function inner<V>(outer: Map<string, Map<string, V>>, root: string): Map<string, V> {
  let map = outer.get(root);
  if (!map) {
    map = new Map();
    outer.set(root, map);
  }
  return map;
}

/** Add `by` to a root's count for a path, dropping what reaches zero. */
function count(counts: Map<string, Map<string, number>>, root: string, relative: string, by: number): void {
  const paths = inner(counts, root);
  const next = (paths.get(relative) ?? 0) + by;
  if (next > 0) paths.set(relative, next);
  else paths.delete(relative);
  if (paths.size === 0) counts.delete(root);
}

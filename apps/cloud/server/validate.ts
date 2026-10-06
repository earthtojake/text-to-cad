// Input validation shared by REST and MCP: one set of rules, one set of messages.
import { z } from 'zod';
import type { Limits } from './config.ts';
import { badRequest } from './errors.ts';
import { isBuildId } from './ids.ts';

export const VIEWABLE_SUFFIXES = ['.step', '.stp', '.glb', '.stl', '.3mf', '.dxf', '.urdf', '.sdf', '.srdf'];

export const isViewable = (path: string) => VIEWABLE_SUFFIXES.some((suffix) => path.toLowerCase().endsWith(suffix));

/**
 * A file path inside a build: relative, POSIX, normalized. `./` prefixes are dropped;
 * everything else that could escape the workspace or mean two things is refused.
 */
export function normalizePath(raw: unknown, field = 'path'): string {
  if (typeof raw !== 'string') throw badRequest(`${field} must be a string`);
  let value = raw.normalize('NFC');
  while (value.startsWith('./')) value = value.slice(2);
  const show = JSON.stringify(raw.length > 80 ? `${raw.slice(0, 80)}…` : raw);
  if (!value) throw badRequest(`${field} ${show} is empty`);
  if (value.length > 512) throw badRequest(`${field} ${show} is longer than 512 characters`);
  if (/[\u0000-\u001f\u007f]/.test(value)) throw badRequest(`${field} ${show} contains a control character`);
  if (value.includes('\\')) throw badRequest(`${field} ${show} uses a backslash; separate folders with /`);
  if (value.startsWith('/') || /^[A-Za-z]:/.test(value)) throw badRequest(`${field} ${show} is absolute; paths are relative to the build's root`);
  const parts = value.split('/');
  if (parts.length > 32) throw badRequest(`${field} ${show} is nested more than 32 folders deep`);
  for (const part of parts) {
    if (part === '') throw badRequest(`${field} ${show} has an empty folder name (// or a trailing /)`);
    if (part === '.' || part === '..') throw badRequest(`${field} ${show} contains ${part}; paths must stay inside the build`);
    if (part.length > 255) throw badRequest(`${field} ${show} has a name longer than 255 characters`);
    if (part.toLowerCase().startsWith('.cadgen')) throw badRequest(`${field} ${show} is inside .cadgen, which is reserved`);
  }
  return value;
}

export type FileContent = string | { base64: string };

export function decodeContent(path: string, content: unknown): Uint8Array {
  if (typeof content === 'string') return new TextEncoder().encode(content);
  if (content && typeof content === 'object' && typeof (content as { base64?: unknown }).base64 === 'string') {
    const text = (content as { base64: string }).base64.replace(/\s+/g, '');
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(text) || text.length % 4 === 1) throw badRequest(`${path}: base64 content is not valid base64`);
    return new Uint8Array(Buffer.from(text, 'base64'));
  }
  throw badRequest(`${path}: a file's content is text, or {"base64": "..."} for binary files`);
}

export const FileContentSchema = z.union([z.string(), z.object({ base64: z.string() })]);

export const BuildInputSchema = z.object({
  files: z.record(z.string(), FileContentSchema).optional(),
  entry: z.union([z.string(), z.array(z.string())]).optional(),
  base: z.string().optional(),
  delete: z.array(z.string()).optional(),
  title: z.string().optional(),
  pythonpath: z.array(z.string()).optional(),
});

export type BuildInput = z.infer<typeof BuildInputSchema>;

export interface FileRef {
  path: string;
  sha256: string;
  bytes: number;
}

export interface ValidatedBuild {
  /** New contents by path (the base build's untouched files are in `kept`). */
  added: Map<string, Uint8Array>;
  kept: FileRef[];
  entry: string[];
  pythonpath: string[];
  title: string | null;
  base: string | null;
}

export function cleanTitle(raw: unknown): string | null {
  if (raw === undefined || raw === null) return null;
  if (typeof raw !== 'string') throw badRequest('title must be a string');
  const title = raw.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (title.length > 120) throw badRequest('title is longer than 120 characters');
  return title || null;
}

function asList(value: unknown, field: string): unknown[] {
  if (value === undefined || value === null) return [];
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value;
  throw badRequest(`${field} must be a string or a list of strings`);
}

/**
 * Validate a build request against its base (when it names one): the files after the
 * edit, the entry scripts and the caps on both. Contents are decoded here, once.
 */
export function validateBuild(input: unknown, base: { files: FileRef[]; entry: string[]; pythonpath: string[]; title: string | null } | null, limits: Limits): ValidatedBuild {
  const parsed = BuildInputSchema.safeParse(input);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw badRequest(`${issue?.path.join('.') || 'request'}: ${issue?.message ?? 'invalid'}`);
  }
  const request = parsed.data;
  const rawFiles = request.files ?? {};
  const fileCount = Object.keys(rawFiles).length;
  if (fileCount > limits.maxFiles) throw badRequest(`a build may hold at most ${limits.maxFiles} files; this request sends ${fileCount}`, { cap: 'files' });
  if (!base && fileCount === 0) throw badRequest('files is empty: send the model script and every file it reads');
  if (!base && request.delete?.length) throw badRequest('delete removes files from a base build; name the build in base');

  const added = new Map<string, Uint8Array>();
  for (const [rawPath, content] of Object.entries(rawFiles)) {
    const path = normalizePath(rawPath, 'file');
    if (added.has(path)) throw badRequest(`${path} is sent twice`);
    added.set(path, decodeContent(path, content));
  }
  const removed = new Set<string>();
  for (const rawPath of request.delete ?? []) {
    const path = normalizePath(rawPath, 'delete');
    if (!base!.files.some((file) => file.path === path)) throw badRequest(`delete names ${path}, which the base build does not have`);
    removed.add(path);
  }
  const kept = (base?.files ?? []).filter((file) => !removed.has(file.path) && !added.has(file.path));
  const all = [...kept.map((file) => file.path), ...added.keys()];
  if (all.length > limits.maxFiles) throw badRequest(`a build may hold at most ${limits.maxFiles} files; this one would hold ${all.length}`, { cap: 'files' });
  const bytes = kept.reduce((sum, file) => sum + file.bytes, 0) + [...added.values()].reduce((sum, value) => sum + value.byteLength, 0);
  if (bytes > limits.maxInputBytes) {
    throw badRequest(`a build's files may total at most ${limits.maxInputBytes} bytes; this one totals ${bytes}`, { cap: 'input_bytes' });
  }
  checkLayout(all);

  // entry is optional: without one a build runs no code and publishes the CAD files it
  // is sent. An edit keeps its base's entry unless it names one (or [] for none).
  const entry = (request.entry === undefined && base ? base.entry : asList(request.entry, 'entry'))
    .filter((value) => value !== '')
    .map((value) => normalizePath(value, 'entry'));
  if (entry.length > 16) throw badRequest('a build runs at most 16 entry scripts');
  if (entry.length === 0 && !all.some(isViewable)) {
    throw badRequest(
      `this build has no entry and no CAD file to show: name the model script(s) to run in entry (e.g. "src/bracket.py"), ` +
      `or send the CAD files to publish (${VIEWABLE_SUFFIXES.map((suffix) => suffix.slice(1).toUpperCase()).join(', ')}); entry is optional when you do`,
    );
  }
  const present = new Set(all);
  for (const script of entry) {
    if (!script.endsWith('.py')) throw badRequest(`entry ${script} is not a Python script`);
    if (!present.has(script)) throw badRequest(`entry ${script} is not one of the build's files`);
  }
  if (new Set(entry).size !== entry.length) throw badRequest('entry names a script twice');

  const pythonpath = (request.pythonpath === undefined && base ? base.pythonpath : asList(request.pythonpath, 'pythonpath'))
    .map((value) => (value === '.' || value === './' ? '.' : normalizePath(value, 'pythonpath')));
  if (pythonpath.length > 16) throw badRequest('pythonpath holds at most 16 folders');

  const title = request.title !== undefined ? cleanTitle(request.title) : (base?.title ?? null);
  const baseId = request.base ?? null;
  return { added, kept, entry, pythonpath, title, base: baseId };
}

/** Refuse layouts that cannot exist on disk: a path that is both a file and a folder, or two that differ only by case. */
function checkLayout(paths: string[]) {
  const files = new Set(paths);
  const folded = new Map<string, string>();
  for (const path of paths) {
    const key = path.toLowerCase();
    const other = folded.get(key);
    if (other && other !== path) throw badRequest(`${other} and ${path} differ only by case`);
    folded.set(key, path);
    const parts = path.split('/');
    for (let index = 1; index < parts.length; index += 1) {
      const folder = parts.slice(0, index).join('/');
      if (files.has(folder)) throw badRequest(`${folder} is both a file and a folder`);
    }
  }
}

const WITH_VALUE = new Set([
  '--mode', '--section', '--camera', '--display', '--kinematics', '--animation', '--time',
  '--joint-values', '--focus', '--hide', '--width', '--height', '--size-profile',
]);
const BARE = new Set(['--view-labels', '--debug']);

/** Snapshot flags a request may pass through to `cadgen snapshot`; the rest are refused by name. */
export function validateSnapshotArgs(raw: unknown): string[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw) || raw.some((item) => typeof item !== 'string')) throw badRequest('args must be a list of strings');
  const args = raw as string[];
  if (args.length > 32) throw badRequest('args holds at most 32 items');
  const out: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    const item = args[index];
    if (item.length > 4096) throw badRequest('a snapshot argument is longer than 4096 characters');
    const [flag, inline] = item.includes('=') ? [item.slice(0, item.indexOf('=')), item.slice(item.indexOf('=') + 1)] : [item, undefined];
    if (BARE.has(flag) && inline === undefined) {
      out.push(item);
      continue;
    }
    if (!WITH_VALUE.has(flag)) {
      throw badRequest(`snapshot argument ${JSON.stringify(item)} is not allowed; use ${[...WITH_VALUE, ...BARE].join(', ')}`);
    }
    const value = inline ?? args[index + 1];
    if (value === undefined) throw badRequest(`${flag} needs a value`);
    if ((flag === '--width' || flag === '--height') && !(/^\d+$/.test(value) && Number(value) >= 16 && Number(value) <= 4096)) {
      throw badRequest(`${flag} must be a whole number of pixels from 16 to 4096`);
    }
    if (inline === undefined) {
      out.push(flag, value);
      index += 1;
    } else {
      out.push(item);
    }
  }
  return out;
}

export function validateFormat(raw: unknown): 'png' | 'svg' {
  if (raw === undefined || raw === null || raw === 'png') return 'png';
  if (raw === 'svg') return 'svg';
  throw badRequest('format must be png or svg');
}

export function validateCode(raw: unknown, limits: Limits): string {
  if (typeof raw !== 'string' || !raw.trim()) throw badRequest('code is required: the Python script to run against the build');
  if (Buffer.byteLength(raw) > limits.maxCodeBytes) throw badRequest(`code may be at most ${limits.maxCodeBytes} bytes`);
  return raw;
}

/**
 * A build named by its id or by a link to it: `abc…`, `https://host/b/abc…/STEP/x.step#o1.f2`.
 * Returns the id and, for a link, the file it points at.
 */
export function parseBuildRef(raw: unknown): { id: string; path: string | null } {
  if (typeof raw !== 'string' || !raw.trim()) throw badRequest('build is required: a build id or a link to one');
  const value = raw.trim();
  if (isBuildId(value)) return { id: value, path: null };
  const match = /(?:^|\/)b\/([0-9A-Za-z]{16})(?:\/([^?#]*))?/.exec(value);
  if (!match) throw badRequest(`${JSON.stringify(value.slice(0, 100))} is not a build id or a build link`);
  let path: string | null = null;
  if (match[2]) {
    try {
      path = match[2].split('/').map(decodeURIComponent).join('/');
    } catch {
      throw badRequest('the link has a malformed path');
    }
  }
  return { id: match[1], path: path ? normalizePath(path, 'file') : null };
}

export function parseWait(raw: unknown, maxSeconds: number): number {
  if (raw === undefined || raw === null || raw === '') return 0;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) throw badRequest('wait must be a number of seconds');
  return Math.min(value, maxSeconds);
}

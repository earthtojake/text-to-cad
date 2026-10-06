import { normalizeVirtualPath } from '../build.ts';

/** What the server says of a build (`GET /v1/builds/<id>`), as much of it as the page shows. */
export interface BuildSummary {
  id: string;
  title: string;
  status: string;
  /** The file the build's link opens, as a virtual path, or ''. */
  primaryFile: string;
  /** The build's outputs, as virtual paths. */
  outputs: string[];
}
export interface BuildFile { path: string; bytes: number | null; kind: string }

const text = (value: unknown) => typeof value === 'string' ? value : '';
const record = (value: unknown): Record<string, unknown> | null => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;

async function readJson(url: string, signal?: AbortSignal): Promise<unknown | null> {
  try {
    const response = await fetch(url, { signal, headers: { accept: 'application/json' } });
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    if ((error as { name?: string })?.name === 'AbortError') throw error;
    return null;
  }
}

/** The build, or null where the server has no such route or build (the page then shows the file alone). */
export async function fetchBuild(id: string, signal?: AbortSignal): Promise<BuildSummary | null> {
  const found = record(await readJson(`/v1/builds/${encodeURIComponent(id)}`, signal));
  const build = found ? record(found.build) ?? found : null;
  if (!build) return null;
  const outputs = Array.isArray(build.outputs) ? build.outputs.map(item => normalizeVirtualPath(text(record(item)?.path ?? item))).filter(Boolean) : [];
  return {
    id: text(build.id) || id, title: text(build.title), status: text(build.status),
    primaryFile: normalizeVirtualPath(text(build.primaryFile ?? build.primary_file)) || outputs[0] || '',
    outputs,
  };
}

/** The build's files (`GET /v1/builds/<id>/files`), sources included; null where the server has none to give. */
export async function fetchBuildFiles(id: string, signal?: AbortSignal): Promise<BuildFile[] | null> {
  const found = await readJson(`/v1/builds/${encodeURIComponent(id)}/files`, signal);
  const items = Array.isArray(found) ? found : Array.isArray(record(found)?.files) ? record(found)!.files as unknown[] : null;
  if (!items) return null;
  return items.flatMap(item => {
    const entry = record(item);
    const path = normalizeVirtualPath(text(entry?.path ?? item));
    if (!path) return [];
    const bytes = Number(entry?.bytes);
    return [{ path, bytes: Number.isFinite(bytes) ? bytes : null, kind: text(entry?.kind) || 'other' }];
  });
}

/** One file's text (`GET /v1/builds/<id>/files/<path>`), or null where the server will not give it. */
export async function fetchBuildFile(id: string, path: string, signal?: AbortSignal): Promise<string | null> {
  const virtual = normalizeVirtualPath(path);
  try {
    const response = await fetch(`/v1/builds/${encodeURIComponent(id)}/files${virtual.split('/').map(part => encodeURIComponent(part)).join('/')}`, { signal });
    if (!response.ok) return null;
    const type = response.headers.get('content-type') || '';
    if (type.includes('application/json')) {
      const body = record(await response.json());
      return typeof body?.content === 'string' ? body.content : typeof body?.text === 'string' ? body.text : null;
    }
    return await response.text();
  } catch (error) {
    if ((error as { name?: string })?.name === 'AbortError') throw error;
    return null;
  }
}

export interface WorkspaceResourcePathArgs {
  /** Absolute workspace root. Resolution fails closed when this is missing. */
  workspacePath: string | undefined;
  /** Absolute path of the document that references the resource. */
  containingFilePath: string;
  /** The raw resource reference (src/href/url) from the document. */
  resourcePath: string;
}

export function resolveWorkspaceResourcePath(args: WorkspaceResourcePathArgs): string | null {
  const { workspacePath, containingFilePath, resourcePath } = args;
  const cleanSrc = resourcePath.trim().replace(/\\/g, '/').split('#')[0]?.split('?')[0] ?? '';
  if (!cleanSrc) return null;
  if (/^[a-z][a-z0-9+.-]*:/i.test(cleanSrc)) return null;
  if (cleanSrc.startsWith('//') || cleanSrc.startsWith('#')) return null;
  if (!workspacePath) return null;

  const root = splitAbsolutePath(workspacePath.replace(/\/+$/, ''));
  if (!root) return null;

  let baseSegments: string[];
  if (cleanSrc.startsWith('/')) {
    baseSegments = root.segments.slice();
  } else {
    const containing = splitAbsolutePath(containingFilePath);
    if (!containing || containing.prefix !== root.prefix) return null;
    baseSegments = containing.segments.slice(0, -1);
  }

  const relSegments = cleanSrc.replace(/^\/+/, '').split('/');
  const normalized: string[] = [];
  for (const segment of [...baseSegments, ...relSegments]) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      if (normalized.length === 0) return null;
      normalized.pop();
      continue;
    }
    normalized.push(segment);
  }

  if (normalized.length < root.segments.length) return null;
  for (let index = 0; index < root.segments.length; index += 1) {
    if (normalized[index] !== root.segments[index]) return null;
  }

  return root.prefix + normalized.join('/');
}

type AbsoluteParts = { prefix: string; segments: string[] };

function splitAbsolutePath(input: string): AbsoluteParts | null {
  const normalized = input.replace(/\\/g, '/');
  const driveMatch = /^([A-Za-z]:)\//.exec(normalized);
  if (driveMatch) {
    const prefix = `${driveMatch[1]}/`;
    return { prefix, segments: normalized.slice(prefix.length).split('/').filter(Boolean) };
  }
  if (normalized.startsWith('/')) {
    return { prefix: '/', segments: normalized.slice(1).split('/').filter(Boolean) };
  }
  return null;
}

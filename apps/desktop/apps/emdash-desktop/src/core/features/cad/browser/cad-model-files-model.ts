export type CadModelFileRole =
  | 'model'
  | 'source'
  | 'drawing'
  | 'reference'
  | 'analysis'
  | 'validation'
  | 'export';

export interface CadModelFile {
  path: string;
  name: string;
  role: CadModelFileRole;
}

interface FileCandidate {
  path: string;
  type?: string;
}

// Longest suffix stays first for correct stem parsing. Merely sharing a stem
// does not prove that a Python file generated a STEP.
const CAD_SOURCE_SUFFIXES = [
  '.step.py',
  '.stp.py',
  '.implicit.mjs',
  '.implicit.js',
  '.py',
] as const;
const CAD_MODEL_SUFFIXES = ['.step', '.stp'] as const;
const CAD_EXPORT_SUFFIXES = ['.stl', '.3mf', '.glb'] as const;
const DRAWING_SUFFIXES = ['.dxf', '.pdf', '.svg'] as const;
const IMAGE_SUFFIXES = ['.png', '.jpg', '.jpeg', '.webp'] as const;
const RELATED_DIRECTORIES = new Set([
  'drawings',
  'exports',
  'references',
  'analyses',
  'snapshots',
  'validation',
]);
const INTERNAL_DIRECTORIES = new Set([
  '.cad-runtime',
  '.git',
  '__cadgen__',
  '__pycache__',
  'node_modules',
]);

const ROLE_ORDER: Record<CadModelFileRole, number> = {
  model: 0,
  source: 1,
  drawing: 2,
  reference: 3,
  analysis: 4,
  validation: 5,
  export: 6,
};

export function isCadModelSourcePath(path: string): boolean {
  const normalized = normalizePath(path).toLowerCase();
  return CAD_SOURCE_SUFFIXES.some((suffix) => normalized.endsWith(suffix));
}

/**
 * Conventional source fallback when no package descriptor or file catalog is
 * available. cadgen 0.5 uses `bracket.py` beside `bracket.step`.
 */
export function cadDefaultSourcePath(path: string): string | null {
  const normalized = normalizePath(path);
  if (isCadModelSourcePath(normalized)) return normalized;
  return /\.(?:step|stp)$/i.test(normalized) ? normalized.replace(/\.(?:step|stp)$/i, '.py') : null;
}

export function cadModelStemPath(path: string): string {
  const normalized = normalizePath(path);
  const lowercase = normalized.toLowerCase();
  const suffix = [
    ...CAD_SOURCE_SUFFIXES,
    ...CAD_MODEL_SUFFIXES,
    ...CAD_EXPORT_SUFFIXES,
    '.dxf',
  ].find((candidate) => lowercase.endsWith(candidate));
  return suffix ? normalized.slice(0, -suffix.length) : normalized;
}

export function cadModelDirectory(path: string): string {
  const stem = cadModelStemPath(path);
  const separator = stem.lastIndexOf('/');
  return separator < 0 ? '' : stem.slice(0, separator);
}

export function cadModelSourcePath(
  candidates: readonly FileCandidate[],
  activePath: string,
  knownSourcePath?: string | null
): string | null {
  const normalized = normalizePath(activePath);
  if (isCadModelSourcePath(normalized)) {
    return normalized;
  }
  if (!knownSourcePath || !isCadModelSourcePath(knownSourcePath)) return null;
  const normalizedKnownSource = normalizePath(knownSourcePath);
  return (
    candidates.find(
      (candidate) =>
        (!candidate.type || candidate.type === 'file' || candidate.type === 'symlink') &&
        normalizePath(candidate.path) === normalizedKnownSource
    )?.path ?? null
  );
}

export function selectCadModelFiles(
  candidates: readonly FileCandidate[],
  activePath: string
): CadModelFile[] {
  const modelStem = cadModelStemPath(activePath);
  const modelDirectory = cadModelDirectory(activePath);
  const stemName = fileName(modelStem).toLowerCase();
  const seen = new Set<string>();
  const files: CadModelFile[] = [];

  for (const candidate of candidates) {
    if (candidate.type && candidate.type !== 'file' && candidate.type !== 'symlink') continue;
    const path = normalizePath(candidate.path);
    if (seen.has(path) || containsInternalDirectory(path)) continue;

    const candidateDirectory = directoryName(path);
    const relativeDirectory = relativeDirectoryFrom(modelDirectory, candidateDirectory);
    if (relativeDirectory === null) continue;
    const relatedDirectory = relativeDirectory.split('/').filter(Boolean)[0]?.toLowerCase();
    if (relativeDirectory && (!relatedDirectory || !RELATED_DIRECTORIES.has(relatedDirectory))) {
      continue;
    }

    const name = fileName(path);
    const belongsToAnalysis =
      relatedDirectory === 'analyses' &&
      relativeDirectory.split('/').filter(Boolean)[1]?.toLowerCase() === stemName;
    if (!belongsToAnalysis && !hasModelPrefix(name.toLowerCase(), stemName)) continue;
    const role = classifyRole(path, relativeDirectory);
    if (!role) continue;

    seen.add(path);
    files.push({ path, name, role });
  }

  return files.sort(
    (left, right) =>
      ROLE_ORDER[left.role] - ROLE_ORDER[right.role] || left.name.localeCompare(right.name)
  );
}

function classifyRole(path: string, relativeDirectory: string): CadModelFileRole | null {
  const lowercase = path.toLowerCase();
  const relatedDirectory = relativeDirectory.split('/').filter(Boolean)[0]?.toLowerCase();

  if (CAD_SOURCE_SUFFIXES.some((suffix) => lowercase.endsWith(suffix))) return 'source';
  if (CAD_MODEL_SUFFIXES.some((suffix) => lowercase.endsWith(suffix))) return 'model';
  if (relatedDirectory === 'validation' || relatedDirectory === 'snapshots') return 'validation';
  if (relatedDirectory === 'analyses') return 'analysis';
  if (relatedDirectory === 'references') return 'reference';
  if (relatedDirectory === 'drawings') return 'drawing';
  if (relatedDirectory === 'exports') return 'export';
  if (DRAWING_SUFFIXES.some((suffix) => lowercase.endsWith(suffix))) return 'drawing';
  if (CAD_EXPORT_SUFFIXES.some((suffix) => lowercase.endsWith(suffix))) return 'export';
  if (IMAGE_SUFFIXES.some((suffix) => lowercase.endsWith(suffix))) {
    return /(?:snapshot|validation|evidence|[-_.](?:iso|front|back|top|bottom|left|right))/.test(
      lowercase
    )
      ? 'validation'
      : 'reference';
  }
  if (/\.(?:artifact\.json|manifest\.json|evidence\.md|validation\.md)$/.test(lowercase)) {
    return 'validation';
  }
  return null;
}

function relativeDirectoryFrom(base: string, candidate: string): string | null {
  if (candidate === base) return '';
  const prefix = base ? `${base}/` : '';
  return candidate.startsWith(prefix) ? candidate.slice(prefix.length) : null;
}

function hasModelPrefix(name: string, stemName: string): boolean {
  if (name === stemName) return true;
  if (!name.startsWith(stemName)) return false;
  return ['.', '-', '_'].includes(name[stemName.length] ?? '');
}

function containsInternalDirectory(path: string): boolean {
  return path
    .split('/')
    .filter(Boolean)
    .some((segment) => INTERNAL_DIRECTORIES.has(segment.toLowerCase()));
}

function directoryName(path: string): string {
  const separator = path.lastIndexOf('/');
  return separator < 0 ? '' : path.slice(0, separator);
}

function fileName(path: string): string {
  return path.split('/').pop() ?? path;
}

function normalizePath(path: string): string {
  return path
    .replaceAll('\\', '/')
    .replace(/\/{2,}/g, '/')
    .replace(/\/$/, '');
}

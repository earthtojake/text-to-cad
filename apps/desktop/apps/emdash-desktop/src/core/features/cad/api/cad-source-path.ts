const LEGACY_PYTHON_CAD_SOURCE_RE = /\.(?:step|stp)\.py$/i;

export function isLegacyCadSourcePath(path: string): boolean {
  return LEGACY_PYTHON_CAD_SOURCE_RE.test(path.trim());
}

export function isEditableCadSourcePath(path: string): boolean {
  const normalized = path.trim();
  return /\.py$/i.test(normalized);
}

export function cadSourcePanelPresentation(path: string): {
  readOnly: boolean;
  subtitle: string;
} {
  return {
    readOnly: !isEditableCadSourcePath(path),
    subtitle: 'Model recipe · rebuilds canonical STEP · ⌘S to save',
  };
}

export function migratedCadSourcePath(path: string): string | null {
  const normalized = path.trim();
  return isLegacyCadSourcePath(normalized)
    ? normalized.replace(/\.(?:step|stp)\.py$/i, '.py')
    : null;
}

export function canonicalCadModelPathForLegacySource(path: string): string | null {
  const normalized = path.trim();
  return isLegacyCadSourcePath(normalized) ? normalized.slice(0, -3) : null;
}

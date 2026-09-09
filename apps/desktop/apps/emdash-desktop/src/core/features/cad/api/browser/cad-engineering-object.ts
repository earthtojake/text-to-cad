export type EngineeringObjectKind = 'part' | 'assembly' | 'profile-2d';

export type EngineeringWorkspaceMode =
  | '3d'
  | '2d'
  | 'files'
  | 'drawing'
  | 'source'
  | 'parameters'
  /** Legacy persisted value; analysis outputs now open as ordinary artifacts/files. */
  | 'analysis'
  | 'bom'
  | 'motion'
  | 'instructions';

export type DerivedEngineeringArtifactKind = 'drawing' | 'assembly-guide';

export const ENGINEERING_OBJECT_MODES = {
  part: ['3d', 'drawing', 'parameters', 'source'],
  assembly: ['3d', 'bom', 'motion', 'instructions', 'drawing', 'parameters', 'source'],
  'profile-2d': ['2d', 'parameters', 'source'],
} as const satisfies Record<EngineeringObjectKind, readonly EngineeringWorkspaceMode[]>;

export const DERIVED_ENGINEERING_ARTIFACTS = {
  drawing: { ownerKinds: ['part', 'assembly'], revisionLinked: true },
  'assembly-guide': { ownerKinds: ['assembly'], revisionLinked: true },
} as const satisfies Record<
  DerivedEngineeringArtifactKind,
  { ownerKinds: readonly EngineeringObjectKind[]; revisionLinked: true }
>;

const MODE_LABELS: Record<EngineeringWorkspaceMode, string> = {
  '3d': '3D',
  '2d': '2D',
  files: 'Files',
  drawing: 'Drawing',
  source: 'Source',
  parameters: 'Parameters',
  analysis: 'Analysis',
  bom: 'BOM',
  motion: 'Motion',
  instructions: 'Instructions',
};

export function engineeringWorkspaceModeLabel(mode: EngineeringWorkspaceMode): string {
  return MODE_LABELS[mode];
}

export function availableEngineeringWorkspaceModes(input: {
  kind: EngineeringObjectKind;
  implementedModes: readonly EngineeringWorkspaceMode[];
  hasSource: boolean;
  createdModes?: readonly EngineeringWorkspaceMode[];
}): EngineeringWorkspaceMode[] {
  const applicable = new Set<EngineeringWorkspaceMode>(ENGINEERING_OBJECT_MODES[input.kind]);
  const implemented = new Set(input.implementedModes);
  const created = new Set(input.createdModes ?? []);
  return ENGINEERING_OBJECT_MODES[input.kind].filter((mode) => {
    if (!applicable.has(mode)) return false;
    if (mode === 'source' && !input.hasSource) return false;
    return implemented.has(mode) || created.has(mode);
  });
}

export function cadSourcePath(path: string): string | null {
  const normalized = path.toLowerCase();
  if (
    normalized.endsWith('.step.py') ||
    normalized.endsWith('.stp.py') ||
    normalized.endsWith('.py') ||
    normalized.endsWith('.implicit.js') ||
    normalized.endsWith('.implicit.mjs')
  ) {
    return path;
  }
  return null;
}

const CAD_SUFFIXES = [
  '.step.py',
  '.stp.py',
  '.implicit.js',
  '.implicit.mjs',
  '.step',
  '.stp',
  '.stl',
  '.3mf',
  '.glb',
  '.dxf',
] as const;

export function isCadFilePath(path: string): boolean {
  const normalized = path.trim().toLowerCase();
  return CAD_SUFFIXES.some((suffix) => normalized.endsWith(suffix));
}

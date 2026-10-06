// Content types for stored files. Nothing a build stores is ever served as HTML.
const TYPES: Record<string, string> = {
  '.py': 'text/x-python; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.json': 'application/json',
  '.yaml': 'text/yaml; charset=utf-8',
  '.yml': 'text/yaml; charset=utf-8',
  '.xml': 'application/xml',
  '.urdf': 'application/xml',
  '.srdf': 'application/xml',
  '.sdf': 'application/xml',
  '.xacro': 'application/xml',
  '.step': 'model/step',
  '.stp': 'model/step',
  '.stl': 'model/stl',
  '.3mf': 'model/3mf',
  '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json',
  '.obj': 'model/obj',
  '.dxf': 'image/vnd.dxf',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
};

export function contentTypeFor(path: string): string {
  const match = /\.[^./]+$/.exec(path.toLowerCase());
  return (match && TYPES[match[0]]) || 'application/octet-stream';
}

const TEXT_SUFFIXES = ['.py', '.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.xml', '.urdf', '.srdf', '.sdf', '.xacro', '.toml', '.cfg', '.ini'];

export const isTextPath = (path: string) => TEXT_SUFFIXES.some((suffix) => path.toLowerCase().endsWith(suffix));

export function isPng(bytes: Uint8Array): boolean {
  const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  return bytes.byteLength > 8 && signature.every((value, index) => bytes[index] === value);
}

export function isJpeg(bytes: Uint8Array): boolean {
  return bytes.byteLength > 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
}

export function isSvg(bytes: Uint8Array): boolean {
  const head = new TextDecoder().decode(bytes.subarray(0, 512)).trimStart();
  return head.startsWith('<svg') || head.startsWith('<?xml');
}

/** The image type of `bytes`, judged by content (not by the name it came with), or null. */
export function imageType(bytes: Uint8Array): string | null {
  if (isPng(bytes)) return 'image/png';
  if (isJpeg(bytes)) return 'image/jpeg';
  if (isSvg(bytes)) return 'image/svg+xml';
  return null;
}

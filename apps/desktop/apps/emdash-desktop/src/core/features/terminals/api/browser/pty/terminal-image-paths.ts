import type { NodePlatform } from '@core/primitives/desktop-host/api/host-contract';

// Chromium hands out drag-temp paths under the OS temp tree (e.g.
// /var/folders/.../T/Drops/... on macOS). Those files are deleted right after
// drop/paste completes, before Claude/Codex can read them.
export function isUnstableDropPath(path: string): boolean {
  if (!path) return true;
  if (/^\/(?:private\/)?var\/folders\/.*\/T\/Drops\//.test(path)) return true;
  if (/[\\/](?:tmp|temp)[\\/]/i.test(path) && /(?:drop|chromium|electron)/i.test(path)) {
    return true;
  }
  if (/[\\/]AppData[\\/]Local[\\/]Temp[\\/]/i.test(path)) return true;
  return false;
}

export function isClipboardImageFile(file: File): boolean {
  if (file.type.startsWith('image/')) return true;
  return isHeicLikeFile(file);
}

export function isHeicLikeFile(file: File): boolean {
  const type = file.type.toLowerCase();
  if (type.includes('heic') || type.includes('heif')) return true;
  return /\.(heic|heif)$/i.test(file.name);
}

export function extractClipboardImageFiles(clipboardData: DataTransfer | null): File[] {
  if (!clipboardData?.items) return [];
  const imageFiles: File[] = [];
  const seen = new Set<string>();
  for (const item of clipboardData.items) {
    if (item.kind !== 'file') continue;
    const file = item.getAsFile();
    if (!file || !isClipboardImageFile(file)) continue;

    const fingerprint = `${file.name}\0${file.type}\0${file.size}\0${file.lastModified}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    imageFiles.push(file);
  }

  if (clipboardData.types.some((type) => type.toLowerCase().startsWith('image/'))) {
    // Browser ordering of clipboard items is not guaranteed, so pick a lossless,
    // widely-supported representation deterministically instead of trusting index 0.
    const preferredOrder = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
    const rank = (type: string): number => {
      const index = preferredOrder.indexOf(type.toLowerCase());
      return index === -1 ? Number.MAX_SAFE_INTEGER : index;
    };
    imageFiles.sort((a, b) => rank(a.type) - rank(b.type));
    return imageFiles.slice(0, 1);
  }

  return imageFiles;
}

export function isNearDuplicatePaste(recentPasteAt: number, now = Date.now()): boolean {
  return recentPasteAt > 0 && now >= recentPasteAt && now - recentPasteAt < 250;
}

export function clipboardDataMayContainImage(clipboardData: DataTransfer | null): boolean {
  if (!clipboardData) return false;
  if (extractClipboardImageFiles(clipboardData).length > 0) return true;
  return clipboardData.types.some((type) => {
    const lower = type.toLowerCase();
    return lower.startsWith('image/') || lower.includes('heic') || lower.includes('heif');
  });
}

// POSIX backslash escaping keeps the path a single shell token without quote
// literals that break Claude Code image detection.
export function escapePathForTerminal(path: string): string {
  return path.replace(/([\s'"\\$`!*?()[\]{}|;<>&#~])/g, '\\$1');
}

export function escapeWindowsPathForTerminal(path: string): string {
  return `"${path.replace(/"/g, '""')}"`;
}

export function formatTerminalImagePaths(paths: string[], platform: NodePlatform): string {
  if (platform === 'win32') {
    return paths.map(escapeWindowsPathForTerminal).join(' ');
  }
  return paths.map(escapePathForTerminal).join(' ');
}

export function wrapAsBracketedPaste(text: string): string {
  return `\x1b[200~${text}\x1b[201~`;
}

export function buildTerminalImageInjection(paths: string[], platform: NodePlatform): string {
  const formatted = formatTerminalImagePaths(paths, platform);
  return wrapAsBracketedPaste(formatted);
}

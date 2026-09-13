export function copyNameForConflict(name: string, existingNames: ReadonlySet<string>): string {
  const trimmed = name.trim();
  if (!existingNames.has(trimmed)) return trimmed;

  const { stem, extension } = splitCopyName(trimmed);
  let index = 1;
  while (true) {
    const suffix = index === 1 ? ' copy' : ` copy ${index}`;
    const candidate = `${stem}${suffix}${extension}`;
    if (!existingNames.has(candidate)) return candidate;
    index += 1;
  }
}

function splitCopyName(name: string): { stem: string; extension: string } {
  const dotIndex = name.lastIndexOf('.');
  if (dotIndex <= 0) return { stem: name, extension: '' };
  return {
    stem: name.slice(0, dotIndex),
    extension: name.slice(dotIndex),
  };
}

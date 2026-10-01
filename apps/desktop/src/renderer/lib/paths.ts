/** The last segment of a path, `/` or `\` separated; the path itself when it has none. */
export function basename(file: string): string {
  return file.split(/[\\/]/).filter(Boolean).pop() ?? file;
}

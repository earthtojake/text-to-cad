export type PathError =
  | { type: 'invalid-path'; input: string; message: string }
  | { type: 'invalid-uri'; input: string; message: string }
  | { type: 'incompatible-root'; input: string; message: string }
  | { type: 'outside-root'; input: string; root: string; message: string };

export function invalidPath(input: string, message: string): PathError {
  return { type: 'invalid-path', input, message };
}

export function invalidUri(input: string, message: string): PathError {
  return { type: 'invalid-uri', input, message };
}

export function incompatibleRoot(input: string, message: string): PathError {
  return { type: 'incompatible-root', input, message };
}

export function outsideRoot(input: string, root: string, message: string): PathError {
  return { type: 'outside-root', input, root, message };
}

export function extractErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message: unknown }).message);
  }
  return 'Unknown error';
}

export function formatErrorType(error: unknown): string {
  return error && typeof error === 'object' && 'type' in error
    ? String((error as { type: unknown }).type)
    : String(error);
}

export function splitPath(filePath: string) {
  const parts = filePath.split('/');
  const filename = parts.pop() || filePath;
  const directory = parts.length > 0 ? parts.join('/') : '';
  return { filename, directory };
}

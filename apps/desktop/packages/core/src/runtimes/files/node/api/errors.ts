import type { FsError } from '#runtimes/files/api';

export class FsException extends Error {
  constructor(readonly error: FsError) {
    super(error.type === 'invalid-path' || error.type === 'io' ? error.message : error.type);
    this.name = 'FsException';
  }
}

export function expectedFsError(error: unknown): FsError | undefined {
  return error instanceof FsException ? error.error : undefined;
}

export function toFsError(error: unknown, path: string): FsError {
  const code = (error as NodeJS.ErrnoException | undefined)?.code;
  switch (code) {
    case 'ENOENT':
      return { type: 'not-found', path };
    case 'EACCES':
    case 'EPERM':
      return { type: 'permission-denied', path };
    case 'EEXIST':
      return { type: 'already-exists', path };
    case 'ENOTDIR':
      return { type: 'not-a-directory', path };
    case 'EISDIR':
      return { type: 'is-a-directory', path };
    default:
      return {
        type: 'io',
        path,
        message: error instanceof Error ? error.message : String(error),
      };
  }
}

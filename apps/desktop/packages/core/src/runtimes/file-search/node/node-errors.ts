const ROOT_OPERATIONAL_ERROR_CODES = new Set([
  'EIO',
  'EMFILE',
  'ENFILE',
  'ENOMEM',
  'ENOSPC',
  'ESTALE',
  'ETIMEDOUT',
]);

const PATH_INDEX_OPERATIONAL_ERROR_CODES = new Set([
  'EAGAIN',
  'EBUSY',
  'ECANCELED',
  'EDQUOT',
  'EFBIG',
  'EINTR',
  'EIO',
  'EISDIR',
  'EMLINK',
  'EMFILE',
  'ENFILE',
  'ENODEV',
  'ENOLCK',
  'ENOMEM',
  'ENOSYS',
  'ENOSPC',
  'ENOTEMPTY',
  'ENOTSUP',
  'ENXIO',
  'EOPNOTSUPP',
  'EOVERFLOW',
  'EROFS',
  'ESTALE',
  'ETIMEDOUT',
  'ETXTBSY',
  'EXDEV',
]);

const CONTENT_SCOPE_OPERATIONAL_ERROR_CODES = new Set([
  'EIO',
  'EMFILE',
  'ENFILE',
  'ENOMEM',
  'ENOSPC',
  'ESTALE',
  'ETIMEDOUT',
]);

export function nodeErrorCode(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null) return undefined;
  return typeof (error as NodeJS.ErrnoException).code === 'string'
    ? (error as NodeJS.ErrnoException).code
    : undefined;
}

export function isExpectedRootNodeError(error: unknown): boolean {
  return hasCode(ROOT_OPERATIONAL_ERROR_CODES, error);
}

export function isExpectedPathIndexNodeError(error: unknown): boolean {
  return hasCode(PATH_INDEX_OPERATIONAL_ERROR_CODES, error);
}

export function isExpectedContentScopeNodeError(error: unknown): boolean {
  return hasCode(CONTENT_SCOPE_OPERATIONAL_ERROR_CODES, error);
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function hasCode(codes: ReadonlySet<string>, error: unknown): boolean {
  const code = nodeErrorCode(error);
  return code !== undefined && codes.has(code);
}

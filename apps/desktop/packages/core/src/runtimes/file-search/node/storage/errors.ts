const OPERATIONAL_SQLITE_BASE_CODES = new Set([
  3, // SQLITE_PERM
  4, // SQLITE_ABORT
  5, // SQLITE_BUSY
  6, // SQLITE_LOCKED
  7, // SQLITE_NOMEM
  8, // SQLITE_READONLY
  9, // SQLITE_INTERRUPT
  10, // SQLITE_IOERR
  11, // SQLITE_CORRUPT
  13, // SQLITE_FULL
  14, // SQLITE_CANTOPEN
  15, // SQLITE_PROTOCOL
  18, // SQLITE_TOOBIG
  22, // SQLITE_NOLFS
  23, // SQLITE_AUTH
  26, // SQLITE_NOTADB
]);
const OPERATIONAL_SQLITE_CODES = new Set([
  'SQLITE_PERM',
  'SQLITE_ABORT',
  'SQLITE_BUSY',
  'SQLITE_LOCKED',
  'SQLITE_NOMEM',
  'SQLITE_READONLY',
  'SQLITE_INTERRUPT',
  'SQLITE_IOERR',
  'SQLITE_FULL',
  'SQLITE_CANTOPEN',
  'SQLITE_PROTOCOL',
  'SQLITE_CORRUPT',
  'SQLITE_TOOBIG',
  'SQLITE_NOLFS',
  'SQLITE_AUTH',
  'SQLITE_NOTADB',
]);

export function isOperationalSqliteError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false;
  const candidate = error as { code?: unknown; errcode?: unknown };
  if (typeof candidate.code === 'string' && OPERATIONAL_SQLITE_CODES.has(candidate.code)) {
    return true;
  }
  if (typeof candidate.errcode !== 'number') return false;
  return OPERATIONAL_SQLITE_BASE_CODES.has(candidate.errcode & 0xff);
}

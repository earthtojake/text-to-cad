import { createHash } from 'node:crypto';

const SPACE_INSENSITIVE = new Set([
  '(',
  ')',
  ',',
  ';',
  '.',
  '=',
  '<',
  '>',
  '+',
  '-',
  '*',
  '/',
  '%',
]);

function shouldKeepSpace(previous: string | undefined, next: string): boolean {
  return previous !== undefined && !SPACE_INSENSITIVE.has(previous) && !SPACE_INSENSITIVE.has(next);
}

function normalizeSqlWhitespace(sql: string): string {
  let normalized = '';
  let quote: "'" | '"' | undefined;
  let pendingWhitespace = false;

  for (let index = 0; index < sql.length; index += 1) {
    const character = sql[index];

    if (quote) {
      normalized += character;
      if (character !== quote) continue;
      if (sql[index + 1] === quote) {
        normalized += sql[index + 1];
        index += 1;
      } else {
        quote = undefined;
      }
      continue;
    }

    if (character === "'" || character === '"') {
      if (pendingWhitespace && shouldKeepSpace(normalized.at(-1), character)) normalized += ' ';
      pendingWhitespace = false;
      quote = character;
      normalized += character;
      continue;
    }

    if (/\s/.test(character)) {
      pendingWhitespace = true;
      continue;
    }

    if (pendingWhitespace && shouldKeepSpace(normalized.at(-1), character)) normalized += ' ';
    pendingWhitespace = false;
    normalized += character;
  }

  return normalized.trim();
}

/**
 * Produces a stable positive value accepted by SQLite's `user_version` pragma.
 *
 * Formatting whitespace outside quoted SQL values is ignored. The same SQL
 * passed to `createSchema` should be the input to this function.
 */
export function fingerprintDerivedSchema(sql: string | readonly string[]): number {
  const source = typeof sql === 'string' ? sql : sql.join('\n');
  const digest = createHash('sha256').update(normalizeSqlWhitespace(source), 'utf8').digest();
  const fingerprint = digest.readUInt32BE(0) & 0x7fffffff;
  return fingerprint || 1;
}

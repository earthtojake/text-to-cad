import { describe, expect, it } from 'vitest';
import { fingerprintDerivedSchema } from './fingerprint';

describe('derived SQLite schema fingerprints', () => {
  it('ignores formatting whitespace outside quoted values', () => {
    const compact = `CREATE TABLE cache(id INTEGER PRIMARY KEY,value TEXT DEFAULT 'a  b');`;
    const formatted = `
      CREATE   TABLE cache(
        id INTEGER PRIMARY KEY,
        value TEXT DEFAULT 'a  b'
      );
    `;
    const windowsNewlines = formatted.replaceAll('\n', '\r\n');

    expect(fingerprintDerivedSchema(formatted)).toBe(fingerprintDerivedSchema(compact));
    expect(fingerprintDerivedSchema(windowsNewlines)).toBe(fingerprintDerivedSchema(compact));
  });

  it('preserves whitespace inside quoted values and identifiers', () => {
    expect(fingerprintDerivedSchema(`SELECT 'a b'`)).not.toBe(
      fingerprintDerivedSchema(`SELECT 'a  b'`)
    );
    expect(fingerprintDerivedSchema(`CREATE TABLE "a b" (id INTEGER)`)).not.toBe(
      fingerprintDerivedSchema(`CREATE TABLE "a  b" (id INTEGER)`)
    );
  });

  it('changes for meaningful DDL changes', () => {
    expect(fingerprintDerivedSchema('CREATE TABLE cache (value TEXT)')).not.toBe(
      fingerprintDerivedSchema('CREATE TABLE cache (value BLOB)')
    );
  });

  it('accepts statement arrays and stays within the user_version range', () => {
    const fingerprint = fingerprintDerivedSchema([
      'CREATE TABLE cache (value TEXT);',
      'CREATE INDEX cache_value_idx ON cache(value);',
    ]);

    expect(fingerprint).toBeGreaterThanOrEqual(1);
    expect(fingerprint).toBeLessThan(2 ** 31);
  });
});

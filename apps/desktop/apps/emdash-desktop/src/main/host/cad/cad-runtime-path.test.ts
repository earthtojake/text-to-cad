import { describe, expect, it } from 'vitest';
import { prependPathEntries } from './cad-runtime-path';

describe('prependPathEntries', () => {
  it('puts the runtime directory ahead of the existing PATH', () => {
    const env = prependPathEntries(
      { PATH: '/usr/bin:/bin', HOME: '/h' },
      ['/rt/venv/bin'],
      'darwin'
    );
    expect(env).toEqual({ PATH: '/rt/venv/bin:/usr/bin:/bin', HOME: '/h' });
  });

  it('moves an entry that is already present to the front instead of duplicating it', () => {
    const env = prependPathEntries(
      { PATH: '/usr/bin:/rt/venv/bin:/bin' },
      ['/rt/venv/bin'],
      'linux'
    );
    expect(env.PATH).toBe('/rt/venv/bin:/usr/bin:/bin');
  });

  it('creates PATH when the environment has none', () => {
    expect(prependPathEntries({}, ['/rt/venv/bin'], 'linux')).toEqual({ PATH: '/rt/venv/bin' });
  });

  it('keeps the Windows key spelling and separator', () => {
    const env = prependPathEntries(
      { Path: 'C:\\Windows;C:\\Tools' },
      ['C:\\rt\\venv\\Scripts'],
      'win32'
    );
    expect(env).toEqual({ Path: 'C:\\rt\\venv\\Scripts;C:\\Windows;C:\\Tools' });
  });

  it('ignores empty and repeated entries and returns the same object when nothing applies', () => {
    const env = { PATH: '/bin' };
    expect(prependPathEntries(env, ['', ''], 'linux')).toBe(env);
    expect(prependPathEntries(env, ['/a', '/a'], 'linux').PATH).toBe('/a:/bin');
  });
});

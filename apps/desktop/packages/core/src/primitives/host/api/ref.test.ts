import { describe, expect, it } from 'vitest';
import {
  formatHostRef,
  hostRef,
  hostRefEquals,
  hostRefFromParts,
  hostRefKey,
  hostRefSchema,
  isLocalHostRef,
  LOCAL_HOST_REF,
  parseHostRef,
  sshConnectionIdOf,
} from './index';

describe('host refs', () => {
  it('identifies local and remote runtime hosts', () => {
    const remote = hostRef('remote', 'connection-1');

    expect(LOCAL_HOST_REF).toEqual({ type: 'local', id: 'local' });
    expect(remote).toEqual({ type: 'remote', id: 'connection-1' });
    expect(hostRefEquals(remote, { type: 'remote', id: 'connection-1' })).toBe(true);
    expect(hostRefKey(remote)).toBe('remote:connection-1');
    expect(sshConnectionIdOf(remote)).toBe('connection-1');
    expect(sshConnectionIdOf(LOCAL_HOST_REF)).toBeUndefined();
  });

  it('rejects empty and null-containing ids', () => {
    expect(() => hostRef('remote', '')).toThrow('must not be empty');
    expect(hostRefSchema.safeParse({ type: 'remote', id: 'bad\0id' }).success).toBe(false);
  });

  it('round-trips the canonical serialized form', () => {
    const refs = [LOCAL_HOST_REF, hostRef('remote', 'ssh:connection / one')];

    for (const ref of refs) {
      expect(parseHostRef(formatHostRef(ref))).toEqual(ref);
    }
    expect(formatHostRef(LOCAL_HOST_REF)).toBe('local:local');
    expect(formatHostRef(refs[1])).toBe('remote:ssh%3Aconnection%20%2F%20one');
    expect(hostRefKey(refs[1])).toBe(formatHostRef(refs[1]));
  });

  it('rejects malformed serialized refs', () => {
    expect(() => parseHostRef('local')).toThrow('Invalid serialized host ref');
    expect(() => parseHostRef('unknown:id')).toThrow('Invalid serialized host ref');
    expect(() => parseHostRef('remote:')).toThrow('Invalid serialized host ref');
    expect(() => parseHostRef('local:not-local')).toThrow('Invalid serialized host ref');
    expect(() => parseHostRef('remote:%E0%A4%A')).toThrow('Invalid serialized host ref');
  });

  it('constructs refs from workspace storage parts', () => {
    expect(hostRefFromParts('local', null)).toEqual(LOCAL_HOST_REF);
    expect(hostRefFromParts('remote', 'ssh-1')).toEqual(hostRef('remote', 'ssh-1'));
    expect(() => hostRefFromParts('remote', null)).toThrow('no SSH connection');
    expect(() => hostRefFromParts(null, null)).toThrow('no location');
  });

  it('identifies local refs', () => {
    expect(isLocalHostRef(LOCAL_HOST_REF)).toBe(true);
    expect(isLocalHostRef(hostRef('remote', 'ssh-1'))).toBe(false);
  });
});

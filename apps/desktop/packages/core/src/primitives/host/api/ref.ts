import type { HostRef, HostType, SerializedHostRef } from './types';

export const LOCAL_HOST_REF: HostRef = { type: 'local', id: 'local' };

export function hostRef(type: HostType, id: string): HostRef {
  if (id.length === 0) throw new TypeError('Host id must not be empty');
  if (id.includes('\0')) throw new TypeError('Host id must not contain a null byte');
  return { type, id };
}

export function hostRefEquals(left: HostRef, right: HostRef): boolean {
  return left.type === right.type && left.id === right.id;
}

export function formatHostRef(ref: HostRef): SerializedHostRef {
  return `${ref.type}:${encodeURIComponent(ref.id)}` as SerializedHostRef;
}

/** @deprecated Prefer `formatHostRef`; retained as the canonical map-key spelling. */
export function hostRefKey(ref: HostRef): SerializedHostRef {
  return formatHostRef(ref);
}

export function parseHostRef(value: string): HostRef {
  const separator = value.indexOf(':');
  if (separator <= 0 || separator === value.length - 1) return invalidSerializedHostRef(value);

  const type = value.slice(0, separator);
  if (type !== 'local' && type !== 'remote') return invalidSerializedHostRef(value);

  let id: string;
  try {
    id = decodeURIComponent(value.slice(separator + 1));
  } catch {
    return invalidSerializedHostRef(value);
  }
  if (type === 'local') {
    if (id !== LOCAL_HOST_REF.id) return invalidSerializedHostRef(value);
    return LOCAL_HOST_REF;
  }
  try {
    return hostRef(type, id);
  } catch {
    return invalidSerializedHostRef(value);
  }
}

export function hostRefFromParts(
  location: HostType | null,
  sshConnectionId: string | null
): HostRef {
  if (location === 'local') return LOCAL_HOST_REF;
  if (location === 'remote') {
    if (!sshConnectionId) throw new Error('Remote workspace row has no SSH connection.');
    return hostRef('remote', sshConnectionId);
  }
  throw new Error('Workspace row has no location.');
}

export function isLocalHostRef(ref: HostRef): boolean {
  return ref.type === 'local';
}

export function sshConnectionIdOf(ref: HostRef): string | undefined {
  return ref.type === 'remote' ? ref.id : undefined;
}

function invalidSerializedHostRef(value: string): never {
  throw new TypeError(`Invalid serialized host ref: ${value}`);
}

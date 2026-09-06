import { err, ok, type Result } from '@emdash/shared';
import { hostRef, type HostRef } from '#primitives/host/api';
import { invalidUri, type PathError } from './errors';
import { hostFileRef } from './resource';
import { validateSegment } from './segments';
import type { HostAbsolutePath, HostFileRef, HostPathRoot, ResourceUri } from './types';

const URI_PREFIX = 'emdash-file://';
const URI_VERSION = 'v2';
const LEGACY_URI_VERSION = 'v1';

export function encodeResourceUri(ref: HostFileRef): ResourceUri {
  const rootParts = rootUriParts(ref.path.root);
  const parts = [
    URI_VERSION,
    ref.host.type,
    encodeURIComponent(ref.host.id),
    ...rootParts,
    ...ref.path.segments.map(encodeURIComponent),
  ];
  return `${URI_PREFIX}${parts.join('/')}` as ResourceUri;
}

export function decodeResourceUri(input: string): Result<HostFileRef, PathError> {
  if (!input.startsWith(URI_PREFIX)) {
    return err(invalidUri(input, 'Resource URI must use the emdash-file scheme'));
  }
  const parts = input.slice(URI_PREFIX.length).split('/');
  if (parts.length < 3) return err(invalidUri(input, 'Resource URI is incomplete'));

  const parsed = parseUriHeader(parts, input);
  if (!parsed.success) return parsed;
  const { host, rootKind, rootAndSegments } = parsed.data;

  const decoded = decodeUriParts(rootAndSegments, input);
  if (!decoded.success) return decoded;

  const path = absoluteFromUriParts(rootKind, decoded.data, input);
  if (!path.success) return path;
  return ok(hostFileRef(host, path.data));
}

function parseUriHeader(
  parts: readonly string[],
  input: string
): Result<{ host: HostRef; rootKind: string; rootAndSegments: readonly string[] }, PathError> {
  if (parts[0] === URI_VERSION) {
    const [version, type, encodedId, rootKind, ...rootAndSegments] = parts;
    if (
      version !== URI_VERSION ||
      (type !== 'local' && type !== 'remote') ||
      !encodedId ||
      !rootKind
    ) {
      return err(invalidUri(input, 'Resource URI has an invalid host header'));
    }
    const decodedId = decodeUriComponent(encodedId, input);
    if (!decodedId.success) return decodedId;
    try {
      return ok({ host: hostRef(type, decodedId.data), rootKind, rootAndSegments });
    } catch (error) {
      return err(invalidUri(input, error instanceof Error ? error.message : String(error)));
    }
  }

  const [encodedId, version, rootKind, ...rootAndSegments] = parts;
  if (version !== LEGACY_URI_VERSION || !encodedId || !rootKind) {
    return err(invalidUri(input, 'Unsupported resource URI version'));
  }
  const decodedId = decodeUriComponent(encodedId, input);
  if (!decodedId.success) return decodedId;
  try {
    return ok({
      host: hostRef(decodedId.data === 'local' ? 'local' : 'remote', decodedId.data),
      rootKind,
      rootAndSegments,
    });
  } catch (error) {
    return err(invalidUri(input, error instanceof Error ? error.message : String(error)));
  }
}

export function tryDecodeResourceUri(input: string): HostFileRef | null {
  const decoded = decodeResourceUri(input);
  return decoded.success ? decoded.data : null;
}

export function isResourceUri(input: string): input is ResourceUri {
  return decodeResourceUri(input).success;
}

function rootUriParts(root: HostPathRoot): string[] {
  switch (root.kind) {
    case 'posix':
      return ['posix'];
    case 'drive':
      return ['drive', encodeURIComponent(root.driveLetter.toLowerCase())];
    case 'unc':
      return ['unc', encodeURIComponent(root.server), encodeURIComponent(root.share)];
  }
}

function absoluteFromUriParts(
  rootKind: string,
  parts: readonly string[],
  input: string
): Result<HostAbsolutePath, PathError> {
  switch (rootKind) {
    case 'posix':
      return pathFromRoot({ kind: 'posix' }, parts, input, true);
    case 'drive':
      return drivePathFromParts(parts, input);
    case 'unc':
      return uncPathFromParts(parts, input);
    default:
      return err(invalidUri(input, 'Resource URI has an unknown root kind'));
  }
}

function drivePathFromParts(
  parts: readonly string[],
  input: string
): Result<HostAbsolutePath, PathError> {
  const [driveLetter, ...segments] = parts;
  if (!driveLetter || !/^[A-Za-z]$/u.test(driveLetter)) {
    return err(invalidUri(input, 'Drive resource URI must include a drive letter'));
  }
  return pathFromRoot(
    { kind: 'drive', driveLetter: driveLetter.toUpperCase() },
    segments,
    input,
    false
  );
}

function uncPathFromParts(
  parts: readonly string[],
  input: string
): Result<HostAbsolutePath, PathError> {
  const [server, share, ...segments] = parts;
  if (!server || !share)
    return err(invalidUri(input, 'UNC resource URI must include server and share'));
  const validServer = validateSegment(server, input, {
    normalization: 'preserve',
    allowBackslash: false,
  });
  if (!validServer.success) return validServer;
  const validShare = validateSegment(share, input, {
    normalization: 'preserve',
    allowBackslash: false,
  });
  if (!validShare.success) return validShare;
  return pathFromRoot(
    { kind: 'unc', server: validServer.data, share: validShare.data },
    segments,
    input,
    false
  );
}

function pathFromRoot(
  root: HostPathRoot,
  segments: readonly string[],
  input: string,
  allowBackslash: boolean
): Result<HostAbsolutePath, PathError> {
  const validated: string[] = [];
  for (const segment of segments) {
    const result = validateSegment(segment, input, {
      normalization: 'preserve',
      allowBackslash,
    });
    if (!result.success) return result;
    validated.push(result.data);
  }
  return ok({ root, segments: validated });
}

function decodeUriParts(parts: readonly string[], input: string): Result<string[], PathError> {
  const decoded: string[] = [];
  for (const part of parts) {
    const result = decodeUriComponent(part, input);
    if (!result.success) return result;
    decoded.push(result.data);
  }
  return ok(decoded);
}

function decodeUriComponent(value: string, input: string): Result<string, PathError> {
  try {
    return ok(decodeURIComponent(value));
  } catch {
    return err(invalidUri(input, 'Resource URI contains malformed percent encoding'));
  }
}

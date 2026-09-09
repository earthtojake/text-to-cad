import {
  decodeResourceUri,
  type HostFileRef,
  type HostPathRoot,
} from '@emdash/core/primitives/path/api';
import { err, ok, type Result } from '@emdash/shared';
import type { Facet } from '@core/features/editor/api/browser/open-file-store/facet-handle';
import type { GitRef } from '@core/primitives/git/api';

/**
 * Facet URI codec (spec §7): deterministic encode/decode between a file's
 * identity (HostFileRef / ResourceUri) plus a {@link Facet} and the Monaco
 * model URI string — replacing the legacy `toDiskUri`/`toGitUri` scheme
 * string surgery. Pure string functions with no Monaco dependency, so the
 * codec is unit-testable in the node project.
 *
 * ## URI shape
 *
 * ```
 * emdash-buffer:/v1/<hostType>/<hostId>/<root...>/<segment>...
 * emdash-disk:/v1/...
 * emdash-git:/v1/...?<refPayload>
 * ```
 *
 * The schemes are distinct from the legacy `file://workspace:` / `disk://` /
 * `git://` URIs so both stacks coexist during migration. Root parts mirror
 * the ResourceUri encoding: `posix`, `drive/<letter>`, or
 * `unc/<server>/<share>`.
 *
 * ## Encoding discipline — Monaco `Uri` stability
 *
 * Every codec output must survive `monaco.Uri.parse(uri).toString() === uri`,
 * so that view-state keys and model lookups keyed by codec strings never
 * diverge from Monaco's own spelling. Monaco percent-decodes all components
 * on parse and re-encodes on toString, keeping only RFC 3986 unreserved
 * characters (`A-Za-z0-9-._~`) plus `/` in the path raw. Two consequences:
 *
 * - Path segments and the git-ref payload use *strict* percent-encoding
 *   (unreserved characters raw, everything else uppercase `%XX`), which
 *   Monaco round-trips byte-for-byte.
 * - A literal `/` inside a value cannot be percent-encoded in the path
 *   (Monaco decodes `%2F` and then leaves the bare `/` raw, corrupting the
 *   segment structure). Path segments never contain `/` by construction, but
 *   host ids and git refs (branch names with slashes) may — so those use a
 *   tilde escape into the unreserved alphabet (`~XX` per UTF-8 byte), and the
 *   ref payload lives in the query.
 *
 * Remote URLs on branch refs are not part of facet identity (mirroring
 * `facetSlotKey`/`refsEqual`): a decoded remote branch ref carries an empty
 * remote URL.
 */

export type FacetUriError = { type: 'invalid-facet-uri'; input: string; message: string };

export type DecodedFacetUri = { ref: HostFileRef; facet: Facet };

const FACET_URI_VERSION = 'v1';

const SCHEME_BY_KIND = {
  buffer: 'emdash-buffer',
  disk: 'emdash-disk',
  git: 'emdash-git',
} as const;

/** Monaco model URI string for one facet of the file identified by `ref`. */
export function encodeFacetUri(ref: HostFileRef, facet: Facet): string {
  const parts = [
    FACET_URI_VERSION,
    ref.host.type,
    tildeEncode(ref.host.id),
    ...rootUriParts(ref.path.root),
    ...ref.path.segments.map(strictPercentEncode),
  ];
  const base = `${SCHEME_BY_KIND[facet.kind]}:/${parts.join('/')}`;
  return facet.kind === 'git' ? `${base}?${encodeGitRefPayload(facet.ref)}` : base;
}

/** Decodes a codec-produced facet URI back to the HostFileRef and facet. */
export function decodeFacetUri(input: string): Result<DecodedFacetUri, FacetUriError> {
  const kind = facetKindForScheme(input);
  if (!kind) return invalid(input, 'Facet URI must use an emdash facet scheme');

  let rest = input.slice(SCHEME_BY_KIND[kind].length + 1);
  if (rest.includes('#')) return invalid(input, 'Facet URI must not contain a fragment');

  let facet: Facet;
  const queryIdx = rest.indexOf('?');
  if (kind === 'git') {
    if (queryIdx < 0) return invalid(input, 'Git facet URI must carry a ref payload');
    const payload = decodeGitRefPayload(rest.slice(queryIdx + 1));
    if (!payload) return invalid(input, 'Git facet URI has a malformed ref payload');
    facet = { kind: 'git', ref: payload };
    rest = rest.slice(0, queryIdx);
  } else {
    if (queryIdx >= 0) return invalid(input, 'Non-git facet URI must not have a query');
    facet = { kind };
  }

  if (!rest.startsWith('/')) return invalid(input, 'Facet URI path must be absolute');
  if (rest.startsWith('//')) return invalid(input, 'Facet URI must not have an authority');
  const [version, hostType, encodedHostId, ...rootAndSegments] = rest.slice(1).split('/');
  if (version !== FACET_URI_VERSION) return invalid(input, 'Unsupported facet URI version');
  if (hostType !== 'local' && hostType !== 'remote') {
    return invalid(input, 'Facet URI has an invalid host type');
  }
  if (!encodedHostId) return invalid(input, 'Facet URI is missing the host id');
  const hostId = tildeDecode(encodedHostId);
  if (hostId === null) return invalid(input, 'Facet URI has a malformed host id');

  // Reassemble the equivalent ResourceUri so root/segment validation stays
  // owned by the path primitives. The strict percent-encoded parts are a
  // superset of the standard encoding, so they pass through unchanged.
  const resourceUri = `emdash-file://v2/${hostType}/${encodeURIComponent(hostId)}/${rootAndSegments.join('/')}`;
  const decoded = decodeResourceUri(resourceUri);
  if (!decoded.success) return invalid(input, decoded.error.message);
  return ok({ ref: decoded.data, facet });
}

function facetKindForScheme(input: string): Facet['kind'] | null {
  for (const kind of ['buffer', 'disk', 'git'] as const) {
    if (input.startsWith(`${SCHEME_BY_KIND[kind]}:`)) return kind;
  }
  return null;
}

function invalid(input: string, message: string): Result<never, FacetUriError> {
  return err({ type: 'invalid-facet-uri', input, message });
}

function rootUriParts(root: HostPathRoot): string[] {
  switch (root.kind) {
    case 'posix':
      return ['posix'];
    case 'drive':
      return ['drive', strictPercentEncode(root.driveLetter.toLowerCase())];
    case 'unc':
      return ['unc', strictPercentEncode(root.server), strictPercentEncode(root.share)];
  }
}

// ---------------------------------------------------------------------------
// Git ref payload — lives in the query component
// ---------------------------------------------------------------------------

/**
 * Tokens joined by `.`; variable parts are tilde-encoded, which never emits
 * a bare `.`, so the separator is unambiguous.
 */
function encodeGitRefPayload(ref: GitRef): string {
  switch (ref.kind) {
    case 'head':
      return 'head';
    case 'staged':
      return 'staged';
    case 'unstaged':
      return 'unstaged';
    case 'commit':
      return `commit.${tildeEncode(ref.sha)}`;
    case 'tag':
      return `tag.${tildeEncode(ref.name)}`;
    case 'branch':
      return ref.branch.type === 'remote'
        ? `branch.remote.${tildeEncode(ref.branch.remote.name)}.${tildeEncode(ref.branch.branch)}`
        : `branch.local.${tildeEncode(ref.branch.branch)}`;
  }
}

function decodeGitRefPayload(payload: string): GitRef | null {
  const tokens = payload.split('.');
  switch (tokens[0]) {
    case 'head':
      return tokens.length === 1 ? { kind: 'head' } : null;
    case 'staged':
      return tokens.length === 1 ? { kind: 'staged' } : null;
    case 'unstaged':
      return tokens.length === 1 ? { kind: 'unstaged' } : null;
    case 'commit': {
      if (tokens.length !== 2) return null;
      const sha = tildeDecode(tokens[1] ?? '');
      return sha === null ? null : { kind: 'commit', sha };
    }
    case 'tag': {
      if (tokens.length !== 2) return null;
      const name = tildeDecode(tokens[1] ?? '');
      return name === null ? null : { kind: 'tag', name };
    }
    case 'branch': {
      if (tokens[1] === 'local' && tokens.length === 3) {
        const branch = tildeDecode(tokens[2] ?? '');
        return branch === null ? null : { kind: 'branch', branch: { type: 'local', branch } };
      }
      if (tokens[1] === 'remote' && tokens.length === 4) {
        const remote = tildeDecode(tokens[2] ?? '');
        const branch = tildeDecode(tokens[3] ?? '');
        if (remote === null || branch === null) return null;
        return {
          kind: 'branch',
          branch: { type: 'remote', branch, remote: { name: remote, url: '' } },
        };
      }
      return null;
    }
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Escaping helpers
// ---------------------------------------------------------------------------

/**
 * RFC 3986 strict percent-encoding: unreserved characters stay raw, all
 * others become uppercase `%XX` UTF-8 escapes. Exactly the set Monaco's
 * `Uri.toString()` re-encodes, so parse/format round-trips byte-for-byte.
 * Only safe for values that cannot contain `/` (path segments).
 */
function strictPercentEncode(value: string): string {
  return encodeURIComponent(value).replace(
    /[!'()*]/g,
    (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`
  );
}

const TILDE_SAFE = /^[A-Za-z0-9_-]$/;

/**
 * Escapes into the unreserved alphabet only (`A-Za-z0-9_~-`): safe characters
 * stay raw, everything else (including `/`, `.`, and `~` itself) becomes
 * `~xx` per UTF-8 byte. Monaco never rewrites unreserved characters, so this
 * survives in any URI component — used where values may contain `/`.
 */
function tildeEncode(value: string): string {
  let out = '';
  for (const char of value) {
    if (TILDE_SAFE.test(char)) {
      out += char;
    } else {
      for (const byte of new TextEncoder().encode(char)) {
        out += `~${byte.toString(16).padStart(2, '0')}`;
      }
    }
  }
  return out;
}

function tildeDecode(value: string): string | null {
  const bytes: number[] = [];
  for (let i = 0; i < value.length; i += 1) {
    const char = value[i] ?? '';
    if (char === '~') {
      const hex = value.slice(i + 1, i + 3);
      if (!/^[0-9a-f]{2}$/.test(hex)) return null;
      bytes.push(Number.parseInt(hex, 16));
      i += 2;
    } else if (TILDE_SAFE.test(char)) {
      bytes.push(char.charCodeAt(0));
    } else {
      return null;
    }
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(bytes));
  } catch {
    return null;
  }
}

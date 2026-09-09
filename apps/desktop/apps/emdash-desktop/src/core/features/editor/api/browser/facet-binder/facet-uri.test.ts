import { hostRef } from '@emdash/core/primitives/host/api';
import {
  encodeResourceUri,
  hostFileRef,
  resourceKeyFromFileRef,
  type HostFileRef,
} from '@emdash/core/primitives/path/api';
import { describe, expect, it } from 'vitest';
import type { Facet } from '@core/features/editor/api/browser/open-file-store/facet-handle';
import { refsEqual, type GitRef } from '@core/primitives/git/api';
import { decodeFacetUri, encodeFacetUri } from './facet-uri';

const BUFFER: Facet = { kind: 'buffer' };
const DISK: Facet = { kind: 'disk' };

function posixRef(segments: string[], host = hostRef('local', 'local')): HostFileRef {
  return hostFileRef(host, { root: { kind: 'posix' }, segments });
}

function gitFacet(ref: GitRef): Facet {
  return { kind: 'git', ref };
}

function roundTrip(ref: HostFileRef, facet: Facet): void {
  const uri = encodeFacetUri(ref, facet);
  const decoded = decodeFacetUri(uri);
  expect(decoded.success, `decode failed for ${uri}`).toBe(true);
  if (!decoded.success) return;
  expect(resourceKeyFromFileRef(decoded.data.ref)).toBe(resourceKeyFromFileRef(ref));
  expect(encodeResourceUri(decoded.data.ref)).toBe(encodeResourceUri(ref));
  expect(decoded.data.facet.kind).toBe(facet.kind);
  if (facet.kind === 'git' && decoded.data.facet.kind === 'git') {
    expect(refsEqual(decoded.data.facet.ref, facet.ref)).toBe(true);
  }
  // Determinism: re-encoding the decoded pair reproduces the same URI.
  expect(encodeFacetUri(decoded.data.ref, decoded.data.facet)).toBe(uri);
}

describe('facet URI codec', () => {
  describe('encoding shape', () => {
    it('derives distinct schemes per facet, distinct from the legacy URIs', () => {
      const ref = posixRef(['repo', 'src', 'index.ts']);
      const buffer = encodeFacetUri(ref, BUFFER);
      const disk = encodeFacetUri(ref, DISK);
      const git = encodeFacetUri(ref, gitFacet({ kind: 'head' }));

      expect(buffer).toBe('emdash-buffer:/v1/local/local/posix/repo/src/index.ts');
      expect(disk).toBe('emdash-disk:/v1/local/local/posix/repo/src/index.ts');
      expect(git).toBe('emdash-git:/v1/local/local/posix/repo/src/index.ts?head');

      // The legacy stack keys models by file:// / disk:// / git:// — none of
      // these may collide while both stacks coexist.
      for (const uri of [buffer, disk, git]) {
        expect(uri.startsWith('file:')).toBe(false);
        expect(uri.startsWith('disk:')).toBe(false);
        expect(uri.startsWith('git:')).toBe(false);
      }
    });

    it('derives distinct URIs per git ref so an entry can hold several git facets', () => {
      const ref = posixRef(['repo', 'file.ts']);
      const head = encodeFacetUri(ref, gitFacet({ kind: 'head' }));
      const staged = encodeFacetUri(ref, gitFacet({ kind: 'staged' }));
      const commit = encodeFacetUri(ref, gitFacet({ kind: 'commit', sha: 'abc123' }));
      expect(new Set([head, staged, commit]).size).toBe(3);
    });

    it('is deterministic', () => {
      const ref = posixRef(['repo', 'a b.ts']);
      expect(encodeFacetUri(ref, BUFFER)).toBe(encodeFacetUri(ref, BUFFER));
    });

    it('emits only Monaco-stable characters', () => {
      // Monaco's Uri.parse/toString keeps unreserved chars and `/` raw and
      // re-encodes everything else as uppercase %XX; codec output must
      // already be in that canonical form (verified against real Monaco in
      // the browser suite).
      const ref = hostFileRef(hostRef('remote', 'ssh: weird/id'), {
        root: { kind: 'posix' },
        segments: ['dir with spaces', 'caf\u00e9 100%.ts'],
      });
      const uri = encodeFacetUri(
        ref,
        gitFacet({
          kind: 'branch',
          branch: { type: 'remote', branch: 'feat/x y', remote: { name: 'origin', url: '' } },
        })
      );
      expect(uri).toMatch(/^emdash-git:[A-Za-z0-9\-._~/?%]+$/);
      for (const escape of uri.matchAll(/%(..)/g)) {
        expect(escape[1]).toMatch(/^[0-9A-F]{2}$/);
      }
    });
  });

  describe('round-trips', () => {
    it('round-trips buffer and disk facets', () => {
      const ref = posixRef(['Users', 'dev', 'repo', 'src', 'index.ts']);
      roundTrip(ref, BUFFER);
      roundTrip(ref, DISK);
    });

    it('round-trips path segments with spaces, unicode, and reserved characters', () => {
      roundTrip(posixRef(['dir with spaces', 'caf\u00e9.ts']), BUFFER);
      roundTrip(posixRef(['100% done', 'a#b?c.ts']), DISK);
      roundTrip(posixRef(["it's (tricky)*!.md"]), BUFFER);
      roundTrip(posixRef(['a%20b.ts']), DISK);
    });

    it('round-trips remote hosts with awkward connection ids', () => {
      roundTrip(posixRef(['home', 'file.ts'], hostRef('remote', 'conn-123')), BUFFER);
      roundTrip(posixRef(['home', 'file.ts'], hostRef('remote', 'ssh:user@host/path')), DISK);
    });

    it('round-trips drive and UNC roots', () => {
      const drive = hostFileRef(hostRef('local', 'local'), {
        root: { kind: 'drive', driveLetter: 'C' },
        segments: ['repo', 'file.ts'],
      });
      roundTrip(drive, BUFFER);

      const unc = hostFileRef(hostRef('local', 'local'), {
        root: { kind: 'unc', server: 'srv', share: 'share' },
        segments: ['repo', 'file.ts'],
      });
      roundTrip(unc, DISK);
    });

    it('round-trips every git ref kind', () => {
      const ref = posixRef(['repo', 'file.ts']);
      roundTrip(ref, gitFacet({ kind: 'head' }));
      roundTrip(ref, gitFacet({ kind: 'staged' }));
      roundTrip(ref, gitFacet({ kind: 'unstaged' }));
      roundTrip(ref, gitFacet({ kind: 'commit', sha: 'deadbeefcafe' }));
      roundTrip(ref, gitFacet({ kind: 'tag', name: 'v1.2.3' }));
      roundTrip(ref, gitFacet({ kind: 'branch', branch: { type: 'local', branch: 'main' } }));
      roundTrip(
        ref,
        gitFacet({
          kind: 'branch',
          branch: { type: 'remote', branch: 'main', remote: { name: 'origin', url: '' } },
        })
      );
    });

    it('round-trips branch names with slashes', () => {
      const ref = posixRef(['repo', 'file.ts']);
      roundTrip(
        ref,
        gitFacet({ kind: 'branch', branch: { type: 'local', branch: 'feat/deep/nesting' } })
      );
      roundTrip(
        ref,
        gitFacet({
          kind: 'branch',
          branch: {
            type: 'remote',
            branch: 'release/2024.1/hotfix',
            remote: { name: 'my/remote', url: '' },
          },
        })
      );
    });

    it('round-trips branch names with dots, tildes, and unicode', () => {
      const ref = posixRef(['repo', 'file.ts']);
      roundTrip(
        ref,
        gitFacet({ kind: 'branch', branch: { type: 'local', branch: 'v1.2.x~test caf\u00e9' } })
      );
    });

    it('drops the remote URL from branch refs (not part of facet identity)', () => {
      const ref = posixRef(['repo', 'file.ts']);
      const facet = gitFacet({
        kind: 'branch',
        branch: {
          type: 'remote',
          branch: 'main',
          remote: { name: 'origin', url: 'git@github.com:a/b.git' },
        },
      });
      const decoded = decodeFacetUri(encodeFacetUri(ref, facet));
      expect(decoded.success).toBe(true);
      if (!decoded.success || decoded.data.facet.kind !== 'git') throw new Error('bad decode');
      const gitRef = decoded.data.facet.ref;
      if (gitRef.kind !== 'branch' || gitRef.branch.type !== 'remote') {
        throw new Error('bad ref shape');
      }
      expect(gitRef.branch.remote.name).toBe('origin');
      expect(gitRef.branch.remote.url).toBe('');
    });
  });

  describe('rejection of malformed URIs', () => {
    const cases: Array<[string, string]> = [
      ['legacy file scheme', 'file://workspace:abc/src/index.ts'],
      ['legacy disk scheme', 'disk://workspace:abc/src/index.ts'],
      ['legacy git scheme', 'git://workspace:abc/HEAD/src/index.ts'],
      ['resource uri', 'emdash-file://v2/local/local/posix/repo/file.ts'],
      ['unknown scheme', 'emdash-nope:/v1/local/local/posix/file.ts'],
      ['empty string', ''],
      ['missing version', 'emdash-buffer:/local/local/posix/file.ts'],
      ['wrong version', 'emdash-buffer:/v9/local/local/posix/file.ts'],
      ['bad host type', 'emdash-buffer:/v1/cloud/local/posix/file.ts'],
      ['missing host id', 'emdash-buffer:/v1/local'],
      ['malformed tilde host id', 'emdash-buffer:/v1/remote/bad~zz/posix/file.ts'],
      ['host id with raw dot', 'emdash-buffer:/v1/remote/bad.id/posix/file.ts'],
      ['authority form', 'emdash-buffer://v1/local/local/posix/file.ts'],
      ['unknown root kind', 'emdash-buffer:/v1/local/local/floppy/file.ts'],
      ['missing root', 'emdash-buffer:/v1/local/local'],
      ['malformed percent escape', 'emdash-buffer:/v1/local/local/posix/%GG.ts'],
      ['fragment present', 'emdash-buffer:/v1/local/local/posix/file.ts#frag'],
      ['query on buffer facet', 'emdash-buffer:/v1/local/local/posix/file.ts?head'],
      ['query on disk facet', 'emdash-disk:/v1/local/local/posix/file.ts?head'],
      ['git without ref payload', 'emdash-git:/v1/local/local/posix/file.ts'],
      ['git with empty ref payload', 'emdash-git:/v1/local/local/posix/file.ts?'],
      ['git with unknown ref kind', 'emdash-git:/v1/local/local/posix/file.ts?weird'],
      ['git head with trailing token', 'emdash-git:/v1/local/local/posix/file.ts?head.extra'],
      ['git commit without sha', 'emdash-git:/v1/local/local/posix/file.ts?commit'],
      ['git branch without type', 'emdash-git:/v1/local/local/posix/file.ts?branch.main'],
      [
        'git branch with malformed tilde escape',
        'emdash-git:/v1/local/local/posix/file.ts?branch.local.fe~zzat',
      ],
      [
        'git branch with raw slash in payload',
        'emdash-git:/v1/local/local/posix/file.ts?branch.local.feat/x',
      ],
    ];

    it.each(cases)('rejects %s', (_label, uri) => {
      const decoded = decodeFacetUri(uri);
      expect(decoded.success).toBe(false);
      if (!decoded.success) expect(decoded.error.type).toBe('invalid-facet-uri');
    });
  });
});

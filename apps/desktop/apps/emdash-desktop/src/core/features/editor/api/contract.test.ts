import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { encodeResourceUri, hostFileRef, parseAbsolute } from '@emdash/core/primitives/path/api';
import { describe, expect, it } from 'vitest';
import { editorContract, editorDomain } from './contract';

const uri = resourceUri('/repo/worktree/src/index.ts');
const rootUri = resourceUri('/repo/worktree');

describe('editorContract', () => {
  it('owns only the crash-recovery buffer surface', () => {
    expect(editorDomain).toBe('editor');
    expect(Object.keys(editorContract)).toEqual(['saveBuffer', 'clearBuffer', 'listBuffers']);
  });

  it('keys buffers by ResourceUri with no workspace identity', () => {
    expect(editorContract.saveBuffer.input.parse({ uri, content: 'draft' })).toEqual({
      uri,
      content: 'draft',
    });
    expect(() =>
      editorContract.saveBuffer.input.parse({
        workspaceId: 'workspace-1',
        relative: 'src/index.ts',
        content: 'draft',
      })
    ).toThrow();
    expect(() =>
      editorContract.clearBuffer.input.parse({ uri: '/repo/worktree/src/index.ts' })
    ).toThrow();
  });

  it('scopes recovery enumeration by an optional root ResourceUri', () => {
    expect(editorContract.listBuffers.input.parse({ root: rootUri })).toEqual({ root: rootUri });
    expect(editorContract.listBuffers.input.parse({})).toEqual({});
  });
});

function resourceUri(path: string) {
  const parsed = parseAbsolute(path, { profile: { style: 'posix' } });
  if (!parsed.success) throw new Error(parsed.error.message);
  return encodeResourceUri(hostFileRef(LOCAL_HOST_REF, parsed.data));
}

import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useWorkspaceDocument } from './useWorkspaceDocument.js';

afterEach(cleanup);

const path = '/projects/one/bracket.step';
const file = { path, name: 'bracket.step', kind: 'file', size: 42, extension: 'step', revision: 'catalog-old' };
const entry = { file: path, hash: 'catalog-new', documentHash: 'document-new' };
const snapshot = { entries: [entry], error: '' };
const subscribe = () => () => {};
const client = { subscribe, getSnapshot: () => snapshot };
const preferenceSnapshot = {};
const preferences = { subscribe, getSnapshot: () => preferenceSnapshot, update: () => {} };
const data = { client, entry, services: { preferences } };

it('uses a document source identity with the live displayed revision', () => {
  const source = { id: 'document-one', resourceRef: (metadata: typeof file) => ({ kind: 'local-file', path: metadata.path, revision: metadata.revision }) };
  const { result } = renderHook(() => useWorkspaceDocument({ view: { source, file }, data }));
  expect(result.current.resource).toEqual({ kind: 'local-file', path, revision: 'document-new' });
});

it('keeps the served-workspace identity when the source has no document identity method', () => {
  const source = { id: 'workspace-one' };
  const { result } = renderHook(() => useWorkspaceDocument({ view: { source, file: { ...file, path: 'parts/bracket.step' } }, data }));
  expect(result.current.resource).toEqual({ kind: 'workspace-file', workspaceId: 'workspace-one', path: 'parts/bracket.step', revision: 'document-new' });
});

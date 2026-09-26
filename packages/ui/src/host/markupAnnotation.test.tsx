import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { expect, it, vi } from 'vitest';
import type { PromptContext, PromptReference } from '@hardcore/core/prompt';
import { ViewerHostContext } from './context.js';
import { createMarkupAnnotationContext, useMarkupAnnotate } from './markupAnnotation.js';
import { testHost } from './testing/host.js';

const page: PromptReference = { resource: { kind: 'workspace-file', workspaceId: 'w', path: 'clip.pdf' }, target: { kind: 'whole-resource' }, label: 'clip.pdf, page 2' };
const image = () => Promise.resolve(new Blob(['png'], { type: 'image/png' }));

it('a markup annotation is its image and a note on it, the note naming the image', () => {
  const context = createMarkupAnnotationContext({ reference: page, image: image(), name: 'clip-markup.png', note: 'move this', id: 'm1' });
  expect(context.parts.map(part => [part.id, part.kind])).toEqual([['m1-image', 'attachment'], ['m1', 'annotation']]);
  const annotation = context.parts[1];
  expect(annotation?.kind === 'annotation' && annotation.attachment).toBe('m1-image');
  expect(annotation?.kind === 'annotation' && annotation.references[0]?.label).toBe('clip.pdf, page 2');
});

it('annotating captures at that moment, delivers, and hands the ink back only when the chat box took it', async () => {
  const delivered: PromptContext[] = [];
  let status: 'added' | 'failed' = 'added';
  const destination = { kind: 'composer' as const, available: true };
  const host = testHost({ promptContext: {
    getSnapshot: () => destination, subscribe: () => () => {},
    deliver: async context => { delivered.push(context); return status === 'added' ? { status, partIds: [] } : { status, message: 'no chat' }; },
  } });
  const wrapper = ({ children }: { children: ReactNode }) => <ViewerHostContext.Provider value={host}>{children}</ViewerHostContext.Provider>;
  const capture = vi.fn(image);
  const onAdded = vi.fn();
  const { result } = renderHook(() => useMarkupAnnotate({ reference: () => page, capture, name: () => 'clip-markup.png', onAdded }), { wrapper });
  expect(result.current.available).toBe(true);
  await act(async () => { await result.current.annotate('move this'); });
  expect(capture).toHaveBeenCalledTimes(1);
  expect(delivered).toHaveLength(1);
  expect(onAdded).toHaveBeenCalledTimes(1);
  status = 'failed';
  await act(async () => { await result.current.annotate('and this'); });
  expect(onAdded).toHaveBeenCalledTimes(1);
});

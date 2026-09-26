import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createPromptContext, referencePart, textPart } from '@hardcore/core/prompt';
import { ViewerHostContext } from './context.js';
import { PromptContextAction } from './PromptContextAction.js';
import { testHost } from './testing/host.js';

afterEach(cleanup);
it.each(['composer', 'clipboard'] as const)('delivers one mixed context to the %s port directly from the gesture', async kind => {
  let encode!: (blob: Blob) => void;
  const image = new Promise<Blob>(resolve => { encode = resolve; });
  const context = createPromptContext([
    referencePart({ resource: { kind: 'workspace-file', workspaceId: 'fixture', path: 'part.step', revision: 'v1' }, target: { kind: 'cad-selector', selectors: ['o1.f2'] } }),
    textPart('Round this edge'),
    { id: 'image', kind: 'attachment', name: 'view.png', mimeType: 'image/png', content: image, about: ['reference'] },
  ]);
  const deliver = vi.fn(async value => { await value.parts[2].content; return { status: kind === 'composer' ? 'added' as const : 'copied' as const, partIds: value.parts.map((part: {id: string}) => part.id) }; });
  const state = { kind, available: true };
  const onResult = vi.fn();
  const host = testHost({ promptContext: { getSnapshot: () => state, subscribe: () => () => {}, deliver } });
  render(<ViewerHostContext.Provider value={host}><PromptContextAction createContext={() => context} onResult={onResult} /></ViewerHostContext.Provider>);
  const button = screen.getByRole('button', { name: kind === 'composer' ? 'Add to prompt' : 'Copy for prompt' });
  fireEvent.click(button);
  expect(deliver).toHaveBeenCalledWith(context);
  expect(onResult).not.toHaveBeenCalled();
  expect((button as HTMLButtonElement).disabled).toBe(true);
  await act(async () => { encode(new Blob(['image'], { type: 'image/png' })); });
  expect(onResult).toHaveBeenCalledWith({ status: kind === 'composer' ? 'added' : 'copied', partIds: ['reference', 'text', 'image'] });
});
it('reports rejected delivery and respects live unavailability', async () => {
  const state = { kind: 'composer' as const, available: true };
  const onResult = vi.fn();
  const host = testHost({ promptContext: { getSnapshot: () => state, subscribe: () => () => {}, deliver: async () => { throw new Error('Destination closed'); } } });
  render(<ViewerHostContext.Provider value={host}><PromptContextAction createContext={() => createPromptContext([textPart('hello')])} onResult={onResult} /></ViewerHostContext.Provider>);
  await act(async () => { fireEvent.click(screen.getByRole('button')); });
  expect(onResult).toHaveBeenCalledWith({ status: 'failed', message: 'Destination closed' });
});
it('says why it is unavailable in its description, with no native title', () => {
  const host = testHost();
  render(<ViewerHostContext.Provider value={host}><PromptContextAction createContext={() => createPromptContext([textPart('hello')])} /></ViewerHostContext.Provider>);
  const button = screen.getByRole('button');
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(button.getAttribute('aria-description')).toBe('Prompt delivery is unavailable in this host.');
  expect(button.hasAttribute('title')).toBe(false);
});

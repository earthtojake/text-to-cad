import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ToolColumn from '../../../../dist/renderers/kit/tools/ToolColumn.js';

// The column alone, for the two cases a renderer with a strip never reaches: a column whose one
// tool's panel needs no strip, and a column with nothing in it to put away. (The column under the
// shell — the strip, its stack, the person's choice and the motion — is `ShellChrome.test.tsx`'s.)
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("a column with no strip has its toggle alone on the strip's line, over the panel it puts away", () => {
  const changes: boolean[] = [];
  const column = (hidden: boolean) => <ToolColumn tools={[]} hidden={hidden} onHiddenChange={next => changes.push(next)}>
    <section aria-label="Animation controls">Play</section>
  </ToolColumn>;
  const { rerender } = render(column(false));
  const row = document.querySelector('[data-cad-tool-row]')!;
  expect([...row.children].map(child => child.hasAttribute('data-cad-tools-toggle'))).toEqual([true]);
  const hide = screen.getByRole('button', { name: 'Hide tools' });
  expect(hide.getAttribute('aria-controls')).toBe(screen.getByRole('region', { name: 'Animation controls' }).parentElement!.id);
  fireEvent.click(hide);
  expect(changes).toEqual([true]);
  // The choice is the caller's to keep: drawn hidden, the panel is put away and the toggle stays put.
  rerender(column(true));
  expect(screen.queryByRole('region', { name: 'Animation controls' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Show tools' }));
  expect(changes).toEqual([true, false]);
});

it('a column with nothing to put away has no toggle and no row, whatever was chosen', () => {
  render(<ToolColumn tools={[]} toggle={false} hidden onHiddenChange={() => {}}><div data-testid="stack" /></ToolColumn>);
  expect(document.querySelector('[data-cad-tool-row]')).toBeNull();
  expect(screen.queryByRole('button', { name: /^(?:Hide|Show) tools$/ })).toBeNull();
  expect(screen.getByTestId('stack').parentElement!.hasAttribute('inert')).toBe(false);
});

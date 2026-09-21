import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { useCadWorkspaceShortcuts } from './useCadWorkspaceShortcuts.js';
afterEach(cleanup);
function View({id, clear}: {id: string; clear: () => void}) {
  const element = useRef<HTMLDivElement>(null);
  useCadWorkspaceShortcuts({ viewerElement: element, selectionActive: true, onClearSelection: clear, tabToolMode: 'references' });
  return <div ref={element} data-testid={id}><button>{id}</button></div>;
}
it('routes keyboard and pointer-owned background shortcuts only to the focused view', () => {
  const one = vi.fn(), two = vi.fn();
  render(<><View id="one" clear={one}/><View id="two" clear={two}/><input aria-label="Composer"/></>);
  fireEvent.pointerDown(screen.getByTestId('one'));
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(one).toHaveBeenCalledTimes(1); expect(two).not.toHaveBeenCalled();
  fireEvent.pointerDown(screen.getByTestId('two'));
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(one).toHaveBeenCalledTimes(1); expect(two).toHaveBeenCalledTimes(1);
  screen.getByRole('textbox').focus();
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });
  expect(two).toHaveBeenCalledTimes(1);
  const button = screen.getByRole('button', {name: 'one'}); button.focus();
  fireEvent.keyDown(button, { key: 'Escape' });
  expect(one).toHaveBeenCalledTimes(2); expect(two).toHaveBeenCalledTimes(1);
});

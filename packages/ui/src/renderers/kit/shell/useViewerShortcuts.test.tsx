import React, { useRef } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useViewerShortcuts } from '../../../../dist/renderers/kit/shell/useViewerShortcuts.js';

afterEach(cleanup);
function Viewer({copy}: {copy: () => boolean}) {
  const element = useRef<HTMLDivElement>(null);
  useViewerShortcuts({ viewerElement: element, escapeActive: false, onEscape: () => {}, onCopy: copy });
  return <div ref={element}><button>Canvas</button><input aria-label="Filter" /></div>;
}
it('copies from its own viewer on Mac and Windows, leaving editable fields and other panes alone', () => {
  const copy = vi.fn(() => true);
  render(<><Viewer copy={copy}/><button>Other pane</button></>);
  fireEvent.keyDown(screen.getByText('Canvas'), {key:'c', metaKey:true});
  fireEvent.keyDown(screen.getByText('Canvas'), {key:'c', ctrlKey:true});
  expect(copy).toHaveBeenCalledTimes(2);
  fireEvent.keyDown(screen.getByLabelText('Filter'), {key:'c', metaKey:true});
  fireEvent.keyDown(screen.getByText('Other pane'), {key:'c', ctrlKey:true});
  expect(copy).toHaveBeenCalledTimes(2);
});

function Zoomed({zoom, onKey}: {zoom: object | null, onKey: () => boolean}) {
  const element = useRef<HTMLDivElement>(null);
  useViewerShortcuts({ viewerElement: element, escapeActive: false, onEscape: () => {}, onKey, zoom: () => zoom });
  return <div ref={element}><button>Canvas</button><input aria-label="Filter" /></div>;
}
it('the zoom keys reach the view zoom, held keys repeating and ⌘= kept from the page, never a text field', () => {
  const zoom = { zoomBy: vi.fn(), fit: vi.fn(), zoomTo100: vi.fn(), zoomToSelection: vi.fn(), selectionAvailable: false };
  const onKey = vi.fn(() => false);
  const view = render(<><Zoomed zoom={zoom} onKey={onKey}/><button>Other pane</button></>);
  const canvas = screen.getByText('Canvas');
  fireEvent.keyDown(canvas, {key:'=', code:'Equal'});
  fireEvent.keyDown(canvas, {key:'=', code:'Equal', repeat:true});
  expect(fireEvent.keyDown(canvas, {key:'=', code:'Equal', metaKey:true})).toBe(false);
  fireEvent.keyDown(canvas, {key:'-', code:'Minus', ctrlKey:true});
  fireEvent.keyDown(canvas, {key:')', code:'Digit0', shiftKey:true});
  fireEvent.keyDown(canvas, {key:'@', code:'Digit2', shiftKey:true});
  expect(zoom.zoomBy.mock.calls).toEqual([[1.5], [1.5], [1.5], [1 / 1.5]]);
  expect([zoom.zoomTo100.mock.calls.length, zoom.zoomToSelection.mock.calls.length]).toEqual([1, 0]);
  // The zoom took its keys; ⇧2 with nothing picked went on to `onKey`.
  expect(onKey).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(screen.getByLabelText('Filter'), {key:'=', code:'Equal'});
  fireEvent.keyDown(screen.getByText('Other pane'), {key:'=', code:'Equal'});
  expect(zoom.zoomBy).toHaveBeenCalledTimes(4);
  // A view that takes no zoom keys now (`zoom()` null) leaves them to the page.
  view.rerender(<><Zoomed zoom={null} onKey={onKey}/><button>Other pane</button></>);
  expect(fireEvent.keyDown(canvas, {key:'=', code:'Equal', metaKey:true})).toBe(true);
  expect(zoom.zoomBy).toHaveBeenCalledTimes(4);
});

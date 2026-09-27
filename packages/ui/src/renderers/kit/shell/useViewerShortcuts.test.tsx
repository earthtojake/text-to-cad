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

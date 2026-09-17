import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FileActivityStatus from '../../dist/file-viewer/FileActivityStatus.js';
Object.assign(globalThis, { React });
afterEach(cleanup);
it('opens a document warning from the generic filename status', () => {
  const onActivate=vi.fn();
  render(<FileActivityStatus activity={{loading:false,label:'Annotations unavailable',title:'The STEP and annotations differ.',tone:'warning',onActivate}} />);
  fireEvent.click(screen.getByRole('button',{name:'Annotations unavailable'}));
  expect(onActivate).toHaveBeenCalledOnce();
  expect(screen.getByRole('button').title).toBe('The STEP and annotations differ.');
});
it('announces progress and removes a completed indicator', () => {
  const {rerender}=render(<FileActivityStatus activity={{loading:true,label:'Opening',title:'Loading 2 of 3 components'}} />);
  expect(screen.getByRole('status').textContent).toBe('Opening');
  rerender(<FileActivityStatus activity={null} />);
  expect(screen.queryByRole('status')).toBeNull();
});

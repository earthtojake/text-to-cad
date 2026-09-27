import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import MissingFileAlert from './MissingFileAlert.js';
Object.assign(globalThis, { React });
afterEach(cleanup);

it('a missing file says so once, and says when the path is outside the served root instead', () => {
  const { rerender } = render(<MissingFileAlert missingFileRef="assemblies/nope.step" rootPath="/models" />);
  expect(screen.getAllByText(/file does not exist/i)).toHaveLength(1);
  expect(screen.getByText('assemblies/nope.step')).toBeTruthy();
  rerender(<MissingFileAlert missingFileRef="/other/checkout/part.step" rootPath="/models" />);
  expect(screen.getAllByText(/outside this viewer's root/i)).toHaveLength(1);
  expect(screen.queryByText(/file does not exist/i)).toBeNull();
});

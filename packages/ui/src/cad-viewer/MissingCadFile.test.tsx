import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MissingCadFile } from '../../dist/cad-viewer/MissingCadFile.js';

beforeEach(() => vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const FILE = '/parts/new.step';

it('a missing file stays missing, and opens once the catalog has it at this very path', () => {
  const reload = vi.fn();
  const view = (entry: object | null) => <MissingCadFile file={FILE} entry={entry as never} reload={reload} />;
  const { rerender } = render(view(null));
  expect(screen.getByText('File does not exist')).toBeTruthy();
  rerender(view({ file: '/parts/other.step', hash: 'a', bytes: 10 }));
  expect(reload).not.toHaveBeenCalled();
  rerender(view({ file: FILE, hash: 'a', bytes: 10 }));
  expect(reload).toHaveBeenCalledTimes(1);
  // The same version of it opens once; another version of it opens again.
  rerender(view({ file: FILE, hash: 'a', bytes: 10 }));
  expect(reload).toHaveBeenCalledTimes(1);
  rerender(view({ file: FILE, hash: 'b', bytes: 12 }));
  expect(reload).toHaveBeenCalledTimes(2);
});

it('with no reload it is the missing-file presentation alone', () => {
  render(<MissingCadFile file={FILE} entry={{ file: FILE, hash: 'a', bytes: 10 } as never} />);
  expect(screen.getByText('File does not exist')).toBeTruthy();
});

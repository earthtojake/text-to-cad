import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { MarkdownEditor } from './MarkdownRenderer.js';

afterEach(cleanup);
test('a live-buffer replacement reaches the visual editor without echoing an edit', async () => {
  const change = vi.fn();
  const view = render(<MarkdownEditor content={'# Original\n\nUser paragraph.\n'} onChange={change} />);
  await waitFor(() => expect(view.getByText('Original')).toBeTruthy());
  view.rerender(<MarkdownEditor content={'# Replaced by agent\n\nNew paragraph.\n'} onChange={change} />);
  await waitFor(() => expect(view.getByText('Replaced by agent')).toBeTruthy());
  expect(view.queryByText('Original')).toBeNull();
  expect(change).not.toHaveBeenCalled();
});

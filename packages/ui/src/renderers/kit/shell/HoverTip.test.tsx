import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import HoverTip, { HOVER_TIP_DELAY_MS } from '../../../../dist/renderers/kit/shell/HoverTip.js';

afterEach(() => { cleanup(); vi.useRealTimers(); });

it('names what the pointer rests on once it has rested a moment, beside it, and goes the moment it leaves', () => {
  vi.useFakeTimers();
  const view = render(<HoverTip tip={{ key: '#C17.1', text: 'C17.1 · +5V', x: 40, y: 60 }} />);
  expect(screen.queryByRole('tooltip')).toBeNull();
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(screen.getByRole('tooltip').textContent).toBe('C17.1 · +5V');
  expect(screen.getByRole('tooltip').style).toMatchObject({ left: '52px', top: '76px' });
  // Passing on to something else waits again; leaving shows nothing.
  view.rerender(<HoverTip tip={{ key: '#R1', text: 'R1 · 330', x: 90, y: 60 }} />);
  expect(screen.queryByRole('tooltip')).toBeNull();
  view.rerender(<HoverTip tip={null} />);
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS * 2); });
  expect(screen.queryByRole('tooltip')).toBeNull();
});

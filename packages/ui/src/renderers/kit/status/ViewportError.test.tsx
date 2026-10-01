import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import ViewportError from './ViewportError.jsx';
import ViewerAlertCard from './ViewerAlertCard.jsx';
import { ViewerMobileContext } from '../../../file-viewer/responsive.js';
Object.assign(globalThis, { React });
afterEach(cleanup);

it('a viewport failure is one line placed by the viewer breakpoint, never the window width', () => {
  const at = (mobile: boolean, message: string) => render(<ViewerMobileContext.Provider value={mobile}><ViewportError message={message} /></ViewerMobileContext.Provider>).container;
  expect(at(false, '').childElementCount).toBe(0);
  const desktop = at(false, 'WebGL context was lost.').querySelector('p')!;
  expect(desktop.textContent).toBe('WebGL context was lost.');
  expect(desktop.className).toMatch(/\btop-20\b/);
  expect(at(true, 'Lost.').querySelector('p')!.className).toMatch(/\btop-24\b/);
  for (const node of document.querySelectorAll('p')) expect(node.className).not.toMatch(/\bsm:/);
  const card = (mobile: boolean) => render(<ViewerMobileContext.Provider value={mobile}>
    <ViewerAlertCard alert={{ severity: 'error', title: 'Broken', message: 'No model' }} hasContent={false} onReload={() => {}} />
  </ViewerMobileContext.Provider>).container.firstElementChild!.className;
  expect(card(true)).toMatch(/\bpx-3\b/);
  expect(card(false)).toMatch(/\bpx-4\b/);
  expect(card(false)).not.toMatch(/\bsm:/);
});

it('says a warning beside the model over it, where it can be put away; with nothing else on screen it stays', () => {
  const warning = { severity: 'warning', title: 'Animation unavailable', message: 'Preview has no routine to play.' };
  render(<ViewerAlertCard alert={warning} hasContent onReload={() => {}} />);
  expect(screen.getByRole('alert').textContent).toContain('Animation unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  expect(screen.queryByRole('alert')).toBeNull();
  cleanup();
  render(<ViewerAlertCard alert={warning} hasContent={false} onReload={() => {}} />);
  expect(screen.getByRole('alert')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
});

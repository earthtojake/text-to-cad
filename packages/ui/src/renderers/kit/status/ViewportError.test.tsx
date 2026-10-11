import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewportError from './ViewportError.jsx';
import ViewerAlertCard, { COPIED_MS, useAlertDismissal } from './ViewerAlertCard.jsx';
import { ViewerMobileContext } from '../../../file-viewer/responsive.js';
import { viewerLinks } from '../../../file-viewer/navigation/links.js';
import { ViewerHostContext } from '../../../host/context.js';
import { testHost } from '../../../host/testing/host.js';
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

/** The card as a frame shows it: its dismissal held beside it (`useAlertDismissal`). */
function FramedCard({ alert, hasContent }: { alert: object, hasContent: boolean }) {
  const { dismissed, dismiss } = useAlertDismissal(alert, { hasContent });
  return <ViewerAlertCard alert={alert} hasContent={hasContent} dismissed={dismissed} onDismiss={dismiss} onReload={() => {}} />;
}

it('says a warning beside the model over it, where it can be put away; with nothing else on screen it stays', () => {
  const warning = { severity: 'warning', title: 'Animation unavailable', message: 'Preview has no routine to play.' };
  render(<FramedCard alert={warning} hasContent />);
  expect(screen.getByRole('alert').textContent).toContain('Animation unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  expect(screen.queryByRole('alert')).toBeNull();
  cleanup();
  render(<FramedCard alert={warning} hasContent={false} />);
  expect(screen.getByRole('alert')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
});

it('offers Retry, and beside it, where the host has a tracker, Report Issue: a new issue saying what the card says', () => {
  const alert = { severity: 'error', title: 'Couldn’t load the model', message: 'No model', reason: 'EOFError', details: 'File: /Users/ada/parts/gear.step', reload: true };
  const onReload = vi.fn();
  const card = (host?: object) => render(<ViewerHostContext.Provider value={host as any ?? null}>
    <ViewerAlertCard alert={alert} hasContent={false} onReload={onReload} file="/Users/ada/parts/gear.step" />
  </ViewerHostContext.Provider>);
  card();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(onReload).toHaveBeenCalledOnce();
  expect(screen.queryByRole('link', { name: 'Report Issue' })).toBeNull();
  cleanup();
  card(testHost({ links: viewerLinks({ version: '0.7.5', issues: '' }) }));
  expect(screen.queryByRole('link', { name: 'Report Issue' })).toBeNull();
  cleanup();
  card(testHost({ links: viewerLinks({ version: '0.7.5' }), environment: { colorScheme: 'light', platform: 'linux' } }));
  const report = new URL(screen.getByRole('link', { name: 'Report Issue' }).getAttribute('href')!);
  expect(`${report.origin}${report.pathname}`).toBe('https://github.com/earthtojake/text-to-cad/issues/new');
  // Opened as "Issue: ", labelled bug; the card's own words and the file's name are the body's, no path of the machine.
  expect(report.searchParams.get('title')).toBe('Issue: ');
  expect(report.searchParams.get('labels')).toBe('bug');
  const body = report.searchParams.get('body')!;
  expect(body).toContain('> **Couldn’t load the model**\n> No model\n> EOFError');
  expect(body).toContain('- File: gear.step\n- CAD: 0.7.5\n- Platform: linux');
  expect(body).toContain('```\nFile: gear.step\n```');
  expect(body).not.toContain('/Users/ada');
});

it('copies the whole of Details, however far they scroll, from the icon in their corner, through the host\'s clipboard', async () => {
  vi.useFakeTimers();
  try {
    const traceback = Array.from({ length: 60 }, (_, line) => `  File "/Users/ada/parts/gear.py", line ${line + 1}, in build`);
    const details = ['File: /Users/ada/parts/gear.step', 'Operation: loading geometry', 'Traceback (most recent call last):', ...traceback,
      'ValueError: the gear has no teeth'].join('\n');
    const alert = { severity: 'error', title: 'Couldn’t prepare the model', message: 'The viewer couldn’t finish processing this model.',
      recovery: 'Try again. If this continues, check the viewer’s terminal output.', details, reload: true };
    const writeText = vi.fn(async (_text: string | Promise<string>) => {});
    const host = testHost({ clipboard: { writeText, readText: async () => '', writeImage: async () => {} } });
    render(<ViewerHostContext.Provider value={host}>
      <ViewerAlertCard alert={alert} hasContent={false} onReload={() => {}} file="/Users/ada/parts/gear.step" />
    </ViewerHostContext.Provider>);
    // Inside Details, at the top-right corner of their box.
    const disclosure = screen.getByText('Details').closest('details')!;
    expect(disclosure.open).toBe(false);
    fireEvent.click(screen.getByText('Details'));
    expect(disclosure.open).toBe(true);
    const copy = screen.getByRole('button', { name: 'Copy error details' });
    expect(disclosure.contains(copy)).toBe(true);
    expect(copy.closest('[data-alert-details]')?.querySelector('pre')?.textContent).toBe(details);

    await act(async () => { fireEvent.click(copy); });
    expect(writeText.mock.calls).toEqual([[details]]);
    // A tick for a moment, then the icon again.
    expect(screen.getByRole('button', { name: 'Error details copied' })).toBe(copy);
    act(() => { vi.advanceTimersByTime(COPIED_MS); });
    expect(screen.getByRole('button', { name: 'Copy error details' })).toBe(copy);
    expect(screen.queryByRole('status')).toBeNull();

    // A clipboard that refuses it is said, never silent; the icon stays, to try again.
    writeText.mockRejectedValueOnce(new DOMException('Write permission denied.', 'NotAllowedError'));
    await act(async () => { fireEvent.click(copy); });
    expect(screen.getByRole('status').textContent).toBe('The details could not be copied. Select them above and copy them.');
    expect(screen.getByRole('button', { name: 'Copy error details' })).toBe(copy);
    await act(async () => { fireEvent.click(copy); });
    expect(writeText).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole('status')).toBeNull();
  } finally { vi.useRealTimers(); }
});

it('offers no copy where there is no clipboard to copy to', () => {
  render(<ViewerAlertCard alert={{ severity: 'error', title: 'Broken', message: 'No model', details: 'File: gear.step' }} hasContent={false} onReload={() => {}} />);
  fireEvent.click(screen.getByText('Details'));
  expect(screen.getByText('File: gear.step')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Copy error details' })).toBeNull();
});

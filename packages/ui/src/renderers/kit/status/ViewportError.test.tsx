import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewportError from './ViewportError.jsx';
import ViewerAlertCard, { useAlertDismissal } from './ViewerAlertCard.jsx';
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

/** A frame with its navbar beside it: the one action it publishes. */
function NavbarFrame({ alert }: { alert: object | null }) {
  const [actions, setActions] = React.useState<readonly any[]>([]);
  const { dismissed, dismiss } = useAlertDismissal(alert, { hasContent: true, onNavigationActionsChange: setActions });
  return <>
    {actions.map(({ id, label, icon: Icon, onInvoke }) => <button key={id} type="button" aria-label={label} onClick={onInvoke}><Icon /></button>)}
    <ViewerAlertCard alert={alert} hasContent dismissed={dismissed} onDismiss={dismiss} onReload={() => {}} body={<p>The body</p>} />
  </>;
}

it('a card put away leaves its icon in the navbar, which brings it back; a changed alert opens again', () => {
  const first = { severity: 'error', blocking: false, title: '1 to fix', message: '', key: 'a' };
  const { rerender } = render(<NavbarFrame alert={first} />);
  expect(screen.getByRole('alert').textContent).toContain('The body');
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  expect(screen.queryByRole('alert')).toBeNull();
  const icon = screen.getByRole('button', { name: '1 to fix' });
  expect(icon.querySelector('svg')!.getAttribute('class')).toMatch(/text-destructive/);
  // The same alert again stays where the person left it; a changed one (its key alone) opens.
  rerender(<NavbarFrame alert={{ ...first }} />);
  expect(screen.queryByRole('alert')).toBeNull();
  rerender(<NavbarFrame alert={{ ...first, key: 'b' }} />);
  expect(screen.getByRole('alert')).toBeTruthy();
  expect(screen.queryByRole('button', { name: '1 to fix' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  fireEvent.click(screen.getByRole('button', { name: '1 to fix' }));
  expect(screen.getByRole('alert')).toBeTruthy();
});

it('a card saying what a design has against it offers no Report Issue', () => {
  const alert = { severity: 'warning', blocking: false, title: '1 suggestion', message: '', report: false };
  render(<ViewerHostContext.Provider value={testHost({ links: viewerLinks({ version: '0.7.5' }) }) as any}>
    <ViewerAlertCard alert={alert} hasContent onReload={() => {}} body={<p>A row</p>} />
  </ViewerHostContext.Provider>);
  expect(screen.getByRole('alert').textContent).toContain('A row');
  expect(screen.queryByRole('link', { name: 'Report Issue' })).toBeNull();
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

import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewerAlertCard from './ViewerAlertCard.jsx';
import { failureAlert, noGeometryAlert } from './loadAlerts.js';
import { buildViewerEditAlert } from '../../step/workbench/viewerAlerts.js';
import { ViewerHostContext } from '../../../host/context.js';
import { testHost } from '../../../host/testing/host.js';
Object.assign(globalThis, { React });
afterEach(cleanup);

const compileFailure = failureAlert('part.step', 'NameError: name "bracket" is not defined', null, true);

it('a build failure keeps its default next step when the host says nothing', () => {
  render(<ViewerHostContext.Provider value={testHost()}>
    <ViewerAlertCard alert={compileFailure} hasContent={false} onReload={() => {}} />
  </ViewerHostContext.Provider>);
  expect(screen.getByText(/viewer’s terminal output/)).toBeTruthy();
  expect(screen.getByText('“part.step” could not be prepared for display.')).toBeTruthy();
  expect(screen.getAllByRole('button').map(button => button.textContent)).toEqual(['Try again']);
});

it('the host supplies the build failure’s words and actions beside Try again', async () => {
  const run = vi.fn(async () => 'Added to the prompt.');
  const recover = vi.fn(() => ({ message: 'The CAD runtime reported an error building this file.', recovery: 'Ask the agent to fix it.', actions: [{ label: 'Ask the agent to fix', run }] }));
  const reload = vi.fn();
  render(<ViewerHostContext.Provider value={testHost({ loadFailures: { recover } })}>
    <ViewerAlertCard alert={compileFailure} hasContent={false} onReload={reload} />
  </ViewerHostContext.Provider>);
  expect(recover).toHaveBeenCalledWith(expect.objectContaining({ kind: 'compile', file: 'part.step', reason: 'NameError: name "bracket" is not defined', blocking: true }));
  expect(screen.queryByText(/terminal output/)).toBeNull();
  expect(screen.getByText('The CAD runtime reported an error building this file.')).toBeTruthy();
  expect(screen.getByText('NameError: name "bracket" is not defined')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(reload).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Ask the agent to fix' }));
  expect(run).toHaveBeenCalledTimes(1);
  expect((await screen.findByRole('status')).textContent).toBe('Added to the prompt.');
});

it('an action that fails says why', async () => {
  const recover = () => ({ actions: [{ label: 'Copy details', run: async () => { throw new Error('Clipboard refused.'); } }] });
  render(<ViewerHostContext.Provider value={testHost({ loadFailures: { recover } })}>
    <ViewerAlertCard alert={compileFailure} hasContent={false} onReload={() => {}} />
  </ViewerHostContext.Provider>);
  expect(screen.getByText(/viewer’s terminal output/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Copy details' }));
  expect((await screen.findByRole('status')).textContent).toBe('Clipboard refused.');
});

it('an empty mesh and a failed edit reach the host with their own kind and file, and keep their words without one', () => {
  const empty = noGeometryAlert('meshes/panel.stl');
  const edit = buildViewerEditAlert({ state: 'failed', file: 'models/bracket.step', error: 'Fillet radius is too large' }, false, true);
  const recover = vi.fn(() => null);
  for (const alert of [empty, edit]) render(<ViewerHostContext.Provider value={testHost({ loadFailures: { recover } })}>
    <ViewerAlertCard alert={alert} hasContent={false} onReload={() => {}} />
  </ViewerHostContext.Provider>);
  expect(recover.mock.calls.map(([failure]: any[]) => [failure.kind, failure.file])).toEqual([['empty', 'meshes/panel.stl'], ['edit', 'models/bracket.step']]);
  expect(screen.getByText('Check that the file contains a model and was saved completely, then reload.')).toBeTruthy();
  expect(screen.getByText('Check the diagnostic in Details, correct the model, then run it again.')).toBeTruthy();
});

it('a host action runs once while pending, and one the host marks unavailable is disabled with its reason', async () => {
  let settle!: (text: string) => void;
  const run = vi.fn(() => new Promise<string>(resolve => { settle = resolve; }));
  const recoverRuns = { elsewhere: vi.fn() };
  const recover = () => ({ actions: [{ label: 'Ask the agent to fix', run }, { label: 'Elsewhere', disabled: true, reason: 'No chat.', run: recoverRuns.elsewhere }] });
  render(<ViewerHostContext.Provider value={testHost({ loadFailures: { recover } })}>
    <ViewerAlertCard alert={compileFailure} hasContent={false} onReload={() => {}} />
  </ViewerHostContext.Provider>);
  const ask = screen.getByRole('button', { name: 'Ask the agent to fix' });
  fireEvent.click(ask);
  fireEvent.click(ask);
  expect(run).toHaveBeenCalledTimes(1);
  expect((ask as HTMLButtonElement).disabled).toBe(true);
  const elsewhere = screen.getByRole('button', { name: 'Elsewhere' }) as HTMLButtonElement;
  // Focusable, described by a reason anyone can read, and inert to a click.
  expect(elsewhere.disabled).toBe(false);
  expect(elsewhere.getAttribute('aria-disabled')).toBe('true');
  expect(elsewhere.hasAttribute('aria-description')).toBe(false);
  expect(elsewhere.hasAttribute('title')).toBe(false);
  expect(document.getElementById(elsewhere.getAttribute('aria-describedby')!)!.textContent).toBe('No chat.');
  elsewhere.focus();
  expect(document.activeElement).toBe(elsewhere);
  fireEvent.click(elsewhere);
  expect(recoverRuns.elsewhere).not.toHaveBeenCalled();
  settle('Added to the prompt.');
  expect((await screen.findByRole('status')).textContent).toBe('Added to the prompt.');
  expect((ask as HTMLButtonElement).disabled).toBe(false);
});

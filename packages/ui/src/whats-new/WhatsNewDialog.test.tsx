import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { I18nProvider } from '../i18n/index.js';
import { WhatsNewDialog, useWhatsNew, type WhatsNewCall, type WhatsNewSettings } from './index.js';

function Host({ call, locale = 'en' }: { call: WhatsNewCall; locale?: string }) {
  const { entry, dismiss } = useWhatsNew(call);
  return <I18nProvider locale={locale}><WhatsNewDialog entry={entry} onDismiss={dismiss} /></I18nProvider>;
}

/** The server's settings: `seen` kept, a PUT adding to it (or failing). */
function server(settings: WhatsNewSettings, { fails = false } = {}) {
  const call = vi.fn<WhatsNewCall>(async seen => {
    if (seen === undefined) return { ...settings, seen: [...settings.seen] };
    if (fails) throw new Error('settings.json cannot be written');
    settings.seen = [...new Set([...settings.seen, ...seen])];
    return { ...settings, seen: [...settings.seen] };
  });
  return { call, settings };
}
const shown = async (call: WhatsNewCall, locale?: string) => {
  render(<Host call={call} locale={locale} />);
  await act(async () => {});
  return screen.queryByRole('dialog');
};

afterEach(cleanup);

it("an update says what's new: the release's title, each item a bold title and its words, and one button, Got it, which keeps it seen", async () => {
  const { call, settings } = server({ seen: [], release: '0.11' });
  const dialog = await shown(call);
  expect(dialog).toBeTruthy();
  expect(screen.getByRole('heading', { name: "What's New (v0.11.0)" })).toBeTruthy();
  expect([...dialog!.querySelectorAll('li strong')].map(node => node.textContent)).toEqual(
    ['KiCad.', 'Blender.', 'MuJoCo.']);
  expect(dialog!.querySelector('li')?.textContent).toContain('Design circuit boards with KiCad: “Design a 9-key macropad PCB.”');
  // What a feature is for and a prompt, never a command.
  expect(dialog!.querySelectorAll('li code')).toHaveLength(0);
  // Read by a screen reader as its title and its notes; the button has the focus.
  expect(dialog!.getAttribute('aria-describedby')).toBe(dialog!.querySelector('ul')!.id);
  expect(screen.getAllByRole('button').map(button => button.textContent)).toEqual(['Got it']);
  expect(document.activeElement?.textContent).toBe('Got it');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Got it' })); });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(call).toHaveBeenLastCalledWith(['0.11']);
  expect(settings.seen).toEqual(['0.11']);
  // Seen: every view on the device reads it so, and shows nothing.
  cleanup();
  expect(await shown(call)).toBeNull();
});

it('Escape and a press outside close it as Got it does', async () => {
  const user = userEvent.setup();
  for (const close of [() => user.keyboard('{Escape}'),
    () => user.click(document.querySelector('[data-slot="dialog-overlay"]')!)]) {
    const { call, settings } = server({ seen: [], release: '0.11' });
    expect(await shown(call)).toBeTruthy();
    await act(async () => { await close(); });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(settings.seen).toEqual(['0.11']);
    cleanup();
  }
});

it('a dismissal that cannot be kept still closes it, and blocks nothing', async () => {
  const { call } = server({ seen: [], release: '0.11' }, { fails: true });
  expect(await shown(call)).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Got it' })); });
  expect(screen.queryByRole('dialog')).toBeNull();
});

it("a new person, a release with no notes, notes seen and a server that keeps none show nothing", async () => {
  for (const settings of [{ seen: ['0.11'], release: '0.11' }, { seen: [], release: '0.10' }, { seen: ['0.11'], release: '0.12' }]) {
    expect(await shown(server(settings).call)).toBeNull();
    cleanup();
  }
  expect(await shown(async () => null)).toBeNull();
  cleanup();
  expect(await shown(async () => { throw new Error('gone'); })).toBeNull();
});

it('dismissed in another view, it closes here once the person comes back to the page', async () => {
  const { call, settings } = server({ seen: [], release: '0.11' });
  expect(await shown(call)).toBeTruthy();
  settings.seen = ['0.11'];
  await act(async () => { fireEvent.focus(window); });
  expect(screen.queryByRole('dialog')).toBeNull();
});

it("reads in the person's language", async () => {
  expect(await shown(server({ seen: [], release: '0.11' }).call, 'ja')).toBeTruthy();
  expect(screen.getByRole('heading', { name: '新機能（v0.11.0）' })).toBeTruthy();
});

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useAutomaticUpdates, type AutomaticUpdates } from './index.js';

function Menu({ call }: { call: (automatic?: boolean) => Promise<AutomaticUpdates> }) {
  const { appSettings } = useAutomaticUpdates(call);
  return <ul>{appSettings?.map(setting => <li key={setting.id}>
    <label><input type="checkbox" checked={setting.checked} disabled={setting.disabled}
      onChange={event => setting.onCheckedChange(event.target.checked)} />{setting.label}</label>
    <span>{setting.info}</span>
  </li>)}</ul>;
}

afterEach(() => { cleanup(); });

it('is a checkbox the server reads, and a click keeps the person’s answer', async () => {
  const call = vi.fn(async (automatic?: boolean): Promise<AutomaticUpdates> =>
    automatic === undefined ? { automatic: true, reason: 'default' } : { automatic, reason: 'choice' });
  render(<Menu call={call} />);
  const box = await screen.findByRole('checkbox', { name: 'Automatic updates' });
  expect((box as HTMLInputElement).checked).toBe(true);
  expect(screen.getByText(/restarts CAD’s server once nothing is running/)).toBeTruthy();
  await act(async () => { fireEvent.click(box); });
  expect(call).toHaveBeenLastCalledWith(false);
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
});

it('one the environment turned off is shown fixed', async () => {
  render(<Menu call={async () => ({ automatic: false, reason: 'environment' })} />);
  const box = await screen.findByRole('checkbox', { name: 'Automatic updates (off in your environment)' });
  expect((box as HTMLInputElement).disabled).toBe(true);
});

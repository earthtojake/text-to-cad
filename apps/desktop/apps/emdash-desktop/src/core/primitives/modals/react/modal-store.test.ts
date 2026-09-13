import { err, ok } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import { ModalStore } from './modal-store';

describe('ModalStore', () => {
  it('resolves completed outcomes and closes the modal', async () => {
    const store = new ModalStore();
    const outcome = store.open('confirmModal', { title: 'Continue?' });

    store.complete(true);

    await expect(outcome).resolves.toEqual(ok(true));
    await Promise.resolve();
    expect(store.isOpen).toBe(false);
  });

  it('keeps the dialog open when a successor opens after a top entry closes in the same turn', async () => {
    const store = new ModalStore();
    const first = store.open('firstModal', {});

    store.complete('done');
    await expect(first).resolves.toEqual(ok('done'));

    const second = store.open('secondModal', {});
    await Promise.resolve();

    expect(store.isOpen).toBe(true);
    expect(store.activeModalId).toBe('secondModal');
    expect(store.stack).toHaveLength(1);

    store.dismiss();
    await expect(second).resolves.toEqual(err({ type: 'modal_dismissed', reason: 'explicit' }));
  });

  it('pushes new modals and dismisses the top entry first', async () => {
    const store = new ModalStore();
    const first = store.open('firstModal', {});
    const second = store.open('secondModal', {});

    expect(store.stack.map((entry) => entry.id)).toEqual(['firstModal', 'secondModal']);
    expect(store.activeModalId).toBe('secondModal');

    store.dismiss();
    await expect(second).resolves.toEqual(err({ type: 'modal_dismissed', reason: 'explicit' }));
    await Promise.resolve();
    expect(store.activeModalId).toBe('firstModal');

    store.complete('done');
    await expect(first).resolves.toEqual(ok('done'));
  });

  it('dismisses every open modal when requested', async () => {
    const store = new ModalStore();
    const first = store.open('firstModal', {});
    const second = store.open('secondModal', {});

    store.dismissAll('navigation');

    await expect(first).resolves.toEqual(err({ type: 'modal_dismissed', reason: 'navigation' }));
    await expect(second).resolves.toEqual(err({ type: 'modal_dismissed', reason: 'navigation' }));
    await Promise.resolve();
    expect(store.isOpen).toBe(false);
  });

  it('reports why an active modal was dismissed', async () => {
    const store = new ModalStore();
    const outcome = store.open('exampleModal', {});

    store.dismiss('navigation');

    await expect(outcome).resolves.toEqual(err({ type: 'modal_dismissed', reason: 'navigation' }));
  });

  it('consumes the previously focused element once', () => {
    const store = new ModalStore();
    const previousFocus = {} as HTMLElement;
    store.previousFocus = previousFocus;

    expect(store.consumePreviousFocus()).toBe(previousFocus);
    expect(store.consumePreviousFocus()).toBeNull();
  });
});

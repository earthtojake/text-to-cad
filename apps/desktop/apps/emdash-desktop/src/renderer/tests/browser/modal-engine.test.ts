import { ok } from '@emdash/shared';
import { afterEach, describe, expect, it } from 'vitest';
import { openModal } from '@core/manifests/browser/modal-api';
import { modalStore } from '@core/primitives/modals/react/modal-store';

afterEach(async () => {
  modalStore.dismiss();
  await Promise.resolve();
});

describe('modal engine', () => {
  it('connects the typed API to the modal store and resolves completed outcomes', async () => {
    const outcome = openModal('commandPaletteModal');

    expect(modalStore.activeModalId).toBe('commandPaletteModal');
    modalStore.complete(undefined);

    await expect(outcome).resolves.toEqual(ok(undefined));
  });
});

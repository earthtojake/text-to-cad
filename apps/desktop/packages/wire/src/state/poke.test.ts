import { describe, expect, it, vi } from 'vitest';
import { pokeChannel } from './poke';

describe('pokeChannel', () => {
  it('supports payload-less channels', () => {
    const listener = vi.fn();
    const channel = pokeChannel('plain');
    const unsubscribe = channel.subscription().subscribe(listener);

    channel.poke();

    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('filters typed payload channels', () => {
    const listener = vi.fn();
    const channel = pokeChannel<{ projectId?: string }>('projects');
    const unsubscribe = channel
      .subscription((payload) => payload.projectId === undefined || payload.projectId === 'one')
      .subscribe(listener);

    channel.poke({ projectId: 'two' });
    channel.poke({ projectId: 'one' });
    channel.poke({});

    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });
});

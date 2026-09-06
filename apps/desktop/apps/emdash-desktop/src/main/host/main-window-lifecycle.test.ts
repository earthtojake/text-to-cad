import { describe, expect, it } from 'vitest';
import { createMainWindowLifecycle } from './main-window-lifecycle';

describe('main window lifecycle', () => {
  it('permanently blocks normal-window recreation after recovery starts', () => {
    const lifecycle = createMainWindowLifecycle();
    expect(lifecycle.canCreate()).toBe(true);

    lifecycle.disableCreation();

    expect(lifecycle.canCreate()).toBe(false);
  });
});

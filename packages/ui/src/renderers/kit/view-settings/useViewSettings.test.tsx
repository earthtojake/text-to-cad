import { renderHook } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

const created = vi.hoisted(() => ({ count: 0 }));
vi.mock('./viewSettingsStore.js', async original => {
  const module = await original<typeof import('./viewSettingsStore.js')>();
  return { ...module, createViewSettingsStore: (...args: Parameters<typeof module.createViewSettingsStore>) => { created.count += 1; return module.createViewSettingsStore(...args); } };
});
const { useViewSettings } = await import('./useViewSettings.js');

test('a renderer that made its own settings hands them to the shell, and no second store is made', () => {
  const own = renderHook(() => useViewSettings('light'));
  expect(created.count).toBe(1);
  expect(own.result.current.store).toBeTruthy();
  const shell = renderHook(() => useViewSettings('light', own.result.current));
  shell.rerender();
  expect(shell.result.current).toBe(own.result.current);
  expect(created.count).toBe(1);
});

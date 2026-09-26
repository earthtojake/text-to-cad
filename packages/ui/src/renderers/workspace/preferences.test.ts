import { expect, test } from 'vitest';
import { createStoredCadPreferences } from './preferences.js';

function memory() {
  const values = new Map<string, string>();
  return { values, storage: { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); } } as unknown as Storage };
}

test('stored preferences read their storage, write the orbit back, and re-read only their own key', () => {
  const { values, storage } = memory();
  values.set('cad-viewer:orbit:v1', JSON.stringify({ speed: 2 }));
  values.set('cad-viewer:theme', 'retired');
  const preferences = createStoredCadPreferences(storage);
  expect(preferences.getSnapshot()).toEqual({ orbit: { speed: 2 }, toolStackWidth: 190 });
  preferences.update({ orbit: { speed: 1.37 } });
  expect(JSON.parse(values.get('cad-viewer:orbit:v1')!)).toEqual({ speed: 1.37 });
  expect(createStoredCadPreferences(storage).getSnapshot().orbit).toEqual({ speed: 1.37 });
  // Another window wrote it: read back and bounded, never written again.
  const heard: unknown[] = [];
  preferences.subscribe(() => heard.push(preferences.getSnapshot().orbit));
  values.set('cad-viewer:orbit:v1', JSON.stringify({ speed: 99 }));
  preferences.storageChanged('cad-viewer:orbit:v1');
  expect(heard).toEqual([{ speed: 5 }]);
  expect(values.get('cad-viewer:orbit:v1')).toBe(JSON.stringify({ speed: 99 }));
  // Someone else's key is theirs; a clear resets to the default.
  const before = preferences.getSnapshot();
  preferences.storageChanged('cad-viewer:theme');
  expect(preferences.getSnapshot()).toBe(before);
  values.clear();
  preferences.storageChanged(null);
  expect(preferences.getSnapshot().orbit).toEqual({ speed: 1 });
  expect(values.size).toBe(0);
});

test('the tool stack width is a stored preference of its own: bounded, written back, and heard from other windows', () => {
  const { values, storage } = memory();
  const preferences = createStoredCadPreferences(storage);
  expect(preferences.getSnapshot().toolStackWidth).toBe(190);
  preferences.update({ toolStackWidth: 240 });
  expect(values.get('cad-viewer:tool-stack-width:v1')).toBe('240');
  expect(values.has('cad-viewer:orbit:v1')).toBe(false);
  expect(createStoredCadPreferences(storage).getSnapshot().toolStackWidth).toBe(240);
  values.set('cad-viewer:tool-stack-width:v1', '12');
  preferences.storageChanged('cad-viewer:tool-stack-width:v1');
  expect(preferences.getSnapshot().toolStackWidth).toBe(160);
  expect(values.get('cad-viewer:tool-stack-width:v1')).toBe('12');
});

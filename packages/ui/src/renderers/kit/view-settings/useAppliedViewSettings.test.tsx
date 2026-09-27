import React, { StrictMode, useEffect, useRef, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { createViewSettingsStore } from './viewSettingsStore.js';
import { useAppliedViewSettings } from './useAppliedViewSettings.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

it('keeps controls authoritative while preparation is pending, including StrictMode remounts', async () => {
  let finish: () => void = () => {};
  let requested: any, settled: any;
  const prepared = new Promise<void>(resolve => { finish = resolve; });
  const viewer = { prepareViewSettings: () => prepared, presentViewSettings: () => Promise.resolve() };
  function Harness() {
    const [store] = useState(() => createViewSettingsStore({}, { lightingQuality: 'preview' }));
    const desired = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot).scene;
    const ref = useRef(viewer);
    const applied = useAppliedViewSettings(desired, 'model', ref);
    requested = desired;
    settled = applied;
    useEffect(() => { if (applied.revision) applied.binding.complete(applied.revision); }, [applied.revision]);
    return <><button onClick={() => store.selectPreset('render')}>Render</button>
      <button onClick={() => store.patch({ lighting: { exposure: 2 } })}>Exposure</button>
      <button onClick={() => store.selectPreset('solid')}>Solid</button>
      <output>{desired.view.mode}:{desired.view.lighting.exposure}</output></>;
  }
  render(<StrictMode><Harness /></StrictMode>);
  fireEvent.click(screen.getByText('Render'));
  fireEvent.click(screen.getByText('Exposure'));
  expect(requested.view.lighting.exposure).toBe(2);
  expect(settled.scene.view.mode).toBe('solid');
  await act(async () => { finish(); });
  await waitFor(() => expect(settled.scene.view.lighting.exposure).toBe(2));
  await waitFor(() => expect(settled.status.pending).toBe(false));
  fireEvent.click(screen.getByText('Solid'));
  await waitFor(() => expect(settled.scene.view.mode).toBe('solid'));
  await waitFor(() => expect(settled.status.pending).toBe(false));
});

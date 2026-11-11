import React, { useState } from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { cleanup, render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { loadXbfDocument } from '@cad/core/lib/xbf/xbfDocument.js';
import { createXbfScene } from '@cad/core/lib/xbf/xbfScene.js';
import MeasureFilterMenu, { measureBadge } from '../../../dist/renderers/kit/tools/measure/MeasureFilterMenu.js';
import { MEASURE_FILTER_DEFAULT } from '../../../dist/renderers/kit/tools/measure/measureFilter.js';
import { MeasureIcon } from '../../../dist/renderers/xbf/XbfSelectionModes.js';
import { xbfMeasurePick } from '../../../dist/renderers/xbf/xbfMeasurePick.js';

// An engine document's Measure menu as a STEP's was: one choice of what a press takes -- All (the
// vertex at an edge's end, else the edge, else the face), or Vertices, Edges or Faces alone -- and
// what each choice then takes on the model, over core's bracket seen from straight above.

Object.assign(globalThis, { React });
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FIXTURES = path.join(path.dirname(createRequire(import.meta.url).resolve('@cad/core/lib/xbf/xbfDocument.js')), '__fixtures__');
const read = (file: string) => fs.readFileSync(path.join(FIXTURES, file));
const ENVIRONMENT = new Uint8Array([...new TextEncoder().encode('#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n'), 255, 255, 255, 128]);
const answer = (body: Uint8Array | Buffer) => ({ ok: true, status: 200, json: async () => JSON.parse(Buffer.from(body).toString('utf8')),
  arrayBuffer: async () => Uint8Array.from(body).buffer });
async function bracket() {
  const fetch = async (url: string) => {
    if (url.endsWith('/api/v1/look')) return answer(read('look.json'));
    if (url.endsWith('/api/v1/look/environment')) return answer(ENVIRONMENT);
    const part = /\/parts\/([^/]+)$/.exec(url);
    return answer(part ? read(`bracket/${part[1]}.xbm`) : read('bracket/structure.json'));
  };
  return createXbfScene(THREE, await loadXbfDocument('http://127.0.0.1:9/api/v1/documents/xbf/bracket', { fetch: fetch as any }));
}

it("Measure's Filter ticks what a press takes, as a STEP's: all, the vertex, else the edge, else the face; each kind alone as it was; any mix; none the free point", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const scene = await bracket();
  // Straight down at the plate's top, 10 px to the millimetre, the origin in the middle of a 600 px view.
  const camera = new THREE.OrthographicCamera(-30, 30, 30, -30, 0.1, 1000);
  camera.position.set(0, 0, 100);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  const view = { camera, width: 600, height: 600 };
  const at = (x: number, y: number) => ({ ray: new THREE.Ray(new THREE.Vector3(x, y, 100), new THREE.Vector3(0, 0, -1)), pointer: { x: 300 + x * 10, y: 300 - y * 10 } });
  // Two pixels in from the top's front-right corner; on its front edge, mid-way; on the top, clear of every edge.
  const spots = { corner: at(17.8, -9.9), edge: at(0, -9.95), face: at(5, 5) };
  const takes = (filter: string[]) => Object.fromEntries(Object.entries(spots).map(([name, { ray, pointer }]) => {
    const pick = xbfMeasurePick({ scene, ray, view, pointer, filter });
    return [name, pick ? (pick.snapKind === 'free' ? 'free' : `${pick.snapKind}${pick.snapKind === 'vertex' ? ` ${pick.point.map((value: number) => Math.round(value)).join(',')}` : ` ${pick.referenceId}`}`) : null];
  }));

  function Strip() {
    const [value, setValue] = useState<readonly string[]>(MEASURE_FILTER_DEFAULT);
    return <>
      <MeasureFilterMenu value={value} onChange={setValue} />
      <MeasureIcon mode={measureBadge(value)} />
      <output data-filter={value.join(',')} />
    </>;
  }
  render(<Strip />);
  const trigger = () => document.querySelector<HTMLElement>('[data-measure-filter-trigger]')!;
  const filter = () => document.querySelector('output')!.dataset.filter!.split(',').filter(Boolean);
  const state = () => ({
    trigger: trigger().getAttribute('aria-label'),
    row: document.querySelector('[data-measure-filter-row]')?.getAttribute('aria-label'),
    badge: document.querySelector('svg[data-tool-icon-base] [data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? '',
    takes: takes(filter()),
  });
  // Its menu is one row, Filter, what is ticked at its right; its submenu All, a rule, then each kind, names alone.
  await user.click(trigger());
  const row = await waitFor(() => document.querySelector<HTMLElement>('[data-measure-filter-row]')!);
  await user.click(row);
  const sub = await waitFor(() => document.querySelector<HTMLElement>('[role=menu][aria-label="Filter"]')!);
  expect([...sub.querySelectorAll('[data-measure-filter], [role=separator]')].map(item => item.getAttribute('data-measure-filter') ?? 'rule'))
    .toEqual(['all', 'rule', 'vertex', 'edge', 'face']);
  expect(sub.querySelectorAll('[data-measure-filter] svg:not(.lucide-check):not(.lucide-minus)')).toHaveLength(0);
  const seen = [state()];
  // jsdom has no geometry for a submenu's pointer grace area: the keyboard ticks, the same handler; the submenu stays up.
  for (const ticks of [['all'], ['vertex'], ['vertex', 'edge'], ['edge', 'face'], ['vertex'], ['edge']]) {
    for (const id of ticks) {
      document.querySelector<HTMLElement>(`[data-measure-filter="${id}"]`)!.focus();
      await user.keyboard('{Enter}');
    }
    seen.push(state());
  }
  const all = { trigger: 'Measure filter: everything', row: 'Filter: All', badge: '', takes: { corner: 'vertex 18,-10,2', edge: 'edge i0/edge/7', face: 'face i0/face/2' } };
  expect(seen).toEqual([
    all,
    // None: a press takes the point on the model as it is, the free point.
    { trigger: 'Measure filter: nothing', row: 'Filter: None', badge: 'filter', takes: { corner: 'free', edge: 'free', face: 'free' } },
    // Vertices alone: an edge's end is its vertex; anywhere else a press takes nothing.
    { trigger: 'Measure filter: Vertices', row: 'Filter: Vertices', badge: 'points', takes: { corner: 'vertex 18,-10,2', edge: null, face: null } },
    // Edges alone: the edge, at its end too; the face's middle is nothing.
    { trigger: 'Measure filter: Edges', row: 'Filter: Edges', badge: 'edges', takes: { corner: 'edge i0/edge/7', edge: 'edge i0/edge/7', face: null } },
    // Faces alone: the face under the pointer, however near an edge.
    { trigger: 'Measure filter: Faces', row: 'Filter: Faces', badge: 'faces', takes: { corner: 'face i0/face/2', edge: 'face i0/face/2', face: 'face i0/face/2' } },
    // Vertices and Faces: an edge's end its vertex, mid-edge the face under it.
    { trigger: 'Measure filter: Vertices, Faces', row: 'Filter: 2 of 3', badge: 'filter', takes: { corner: 'vertex 18,-10,2', edge: 'face i0/face/2', face: 'face i0/face/2' } },
    all,
  ]);
  await user.keyboard('{Escape}');
  // Shift takes the point on the model as it is, whatever the menu says.
  const { ray, pointer } = spots.corner;
  expect(xbfMeasurePick({ scene, ray, view, pointer, filter: MEASURE_FILTER_DEFAULT, free: true })).toMatchObject({ snapKind: 'free', referenceId: '' });
  scene.dispose();
});

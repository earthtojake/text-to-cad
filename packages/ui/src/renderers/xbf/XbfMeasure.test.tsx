import React, { useState } from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { cleanup, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { loadXbfDocument } from '@text-to-cad/core/lib/xbf/xbfDocument.js';
import { createXbfScene } from '@text-to-cad/core/lib/xbf/xbfScene.js';
import MeasureFilterMenu, { MEASURE_MODES } from '../../../dist/renderers/kit/tools/measure/MeasureFilterMenu.js';
import { MEASURE_FILTER_DEFAULT } from '../../../dist/renderers/kit/tools/measure/measureFilter.js';
import { pickModeOf } from '../../../dist/renderers/kit/tools/select/selectFilter.js';
import { MeasureIcon } from '../../../dist/renderers/xbf/XbfSelectionModes.js';
import { xbfMeasurePick } from '../../../dist/renderers/xbf/xbfMeasurePick.js';

// An engine document's Measure menu as a STEP's was: one choice of what a press takes -- All (the
// vertex at an edge's end, else the edge, else the face), or Vertices, Edges or Faces alone -- and
// what each choice then takes on the model, over core's bracket seen from straight above.

Object.assign(globalThis, { React });
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FIXTURES = path.join(path.dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/xbf/xbfDocument.js')), '__fixtures__');
const read = (file: string) => fs.readFileSync(path.join(FIXTURES, file));
const ENVIRONMENT = new Uint8Array([...new TextEncoder().encode('#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n'), 255, 255, 255, 128]);
const answer = (body: Uint8Array | Buffer) => ({ ok: true, status: 200, json: async () => JSON.parse(Buffer.from(body).toString('utf8')),
  arrayBuffer: async () => Uint8Array.from(body).buffer });
async function bracket() {
  const fetch = async (url: string) => {
    if (url.endsWith('/api/look')) return answer(read('look.json'));
    if (url.endsWith('/api/look/environment')) return answer(ENVIRONMENT);
    const part = /\/part\/([^/]+)$/.exec(url);
    return answer(part ? read(`bracket/${part[1]}.xbm`) : read('bracket/structure.json'));
  };
  return createXbfScene(THREE, await loadXbfDocument('http://127.0.0.1:9/api/doc/bracket', { fetch: fetch as any }));
}

it("Measure's menu chooses what a press takes, as a STEP's: All the vertex, else the edge, else the face; each kind alone", async () => {
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
    return [name, pick ? `${pick.snapKind}${pick.snapKind === 'vertex' ? ` ${pick.point.map((value: number) => Math.round(value)).join(',')}` : ` ${pick.referenceId}`}` : null];
  }));

  function Strip() {
    const [value, setValue] = useState<readonly string[]>(MEASURE_FILTER_DEFAULT);
    return <>
      <MeasureFilterMenu value={value} onChange={setValue} />
      <MeasureIcon mode={pickModeOf(value, MEASURE_MODES).id} />
      <output data-filter={value.join(',')} />
    </>;
  }
  render(<Strip />);
  const trigger = () => document.querySelector<HTMLElement>('[data-measure-filter-trigger]')!;
  const state = () => ({
    trigger: trigger().getAttribute('aria-label'),
    badge: document.querySelector('svg[data-tool-icon-base] [data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? '',
    takes: takes(document.querySelector('output')!.dataset.filter!.split(',')),
  });
  const seen = [state()];
  for (const mode of ['vertex', 'edge', 'face', 'all']) {
    await user.click(trigger());
    await user.click(document.querySelector<HTMLElement>(`[data-measure-filter="${mode}"]`)!);
    seen.push(state());
  }
  const all = { trigger: 'Measure filter: everything', badge: '', takes: { corner: 'vertex 18,-10,2', edge: 'edge i0/edge/7', face: 'face i0/face/2' } };
  expect(seen).toEqual([
    all,
    // Vertices: an edge's end is its vertex; anywhere else a press takes nothing.
    { trigger: 'Measure filter: Vertices', badge: 'points', takes: { corner: 'vertex 18,-10,2', edge: null, face: null } },
    // Edges: the edge, at its end too; the face's middle is nothing.
    { trigger: 'Measure filter: Edges', badge: 'edges', takes: { corner: 'edge i0/edge/7', edge: 'edge i0/edge/7', face: null } },
    // Faces: the face under the pointer, however near an edge.
    { trigger: 'Measure filter: Faces', badge: 'faces', takes: { corner: 'face i0/face/2', edge: 'face i0/face/2', face: 'face i0/face/2' } },
    all,
  ]);
  // Shift takes the point on the model as it is, whatever the menu says.
  const { ray, pointer } = spots.corner;
  expect(xbfMeasurePick({ scene, ray, view, pointer, filter: MEASURE_FILTER_DEFAULT, free: true })).toMatchObject({ snapKind: 'free', referenceId: '' });
  scene.dispose();
});

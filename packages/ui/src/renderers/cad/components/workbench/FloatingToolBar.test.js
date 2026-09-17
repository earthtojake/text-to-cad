import assert from 'node:assert/strict';
import test from 'node:test';
import FloatingToolBar from './FloatingToolBar.js';
import { render, elements } from '../../../../../scripts/reactHarness.mjs';

function measureButtons(format, measureSupported) {
  const outer = render(FloatingToolBar, {
    selectedEntry: { file: `part.${format}` }, renderFormat: format,
    selectedMeshData: {}, measureSupported,
  });
  const toolbar = render(outer.tree.type, outer.tree.props);
  const buttons = elements(toolbar.tree).filter(node => node.props.label === 'Measure');
  toolbar.unmount(); outer.unmount();
  return buttons;
}

test('Measure is offered for STEP and meshes, and absent for drawings and robots', () => {
  for (const format of ['step', 'stl', '3mf', 'glb']) assert.equal(measureButtons(format).length, 1, format);
  for (const format of ['dxf', 'urdf', 'srdf', 'sdf']) assert.equal(measureButtons(format).length, 0, format);
});

test('the resolved document capability can disable Measure for an animated mesh', () => {
  assert.equal(measureButtons('glb', false).length, 0);
  assert.equal(measureButtons('glb', true).length, 1);
});

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

test('the floating toolbar contains only interaction tools in every display mode', () => {
  for (const renderMode of [false, true]) {
    const outer = render(FloatingToolBar, {
      selectedEntry: { file: 'part.step' }, renderFormat: 'step', selectedMeshData: {},
      renderMode, selectionFilter: 'all', onSelectionFilterChange() {}, handleSelectTabToolMode() {},
    });
    const toolbar = render(outer.tree.type, outer.tree.props);
    const nodes = elements(toolbar.tree);
    const groups = nodes.filter(node => node.props.role === 'group');
    assert.deepEqual(groups.map(node => node.props['aria-label']), ['Interaction tools']);
    const filter = nodes.find(node => node.type?.name === 'SelectionFilterMenu');
    assert.equal(filter.props.trigger.props.label, 'Select');
    assert.deepEqual(nodes.map(node => node.props.label).filter(Boolean), ['Pan', 'Measure', 'Draw']);
    assert.equal(nodes.some(node => node.props['aria-label'] === 'Zoom controls'), false);
    toolbar.unmount(); outer.unmount();
  }
});

test('fullscreen has no floating controls, even with an active tool', () => {
  const toolbar = render(FloatingToolBar, { selectedEntry: { file: 'part.step' }, previewMode: true, drawToolActive: true });
  assert.equal(toolbar.tree, null);
  toolbar.unmount();
});

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

test('Measure is a STEP tool: no mesh, drawing or robot offers it', () => {
  assert.equal(measureButtons('step').length, 1);
  for (const format of ['stl', '3mf', 'glb', 'dxf', 'urdf', 'srdf', 'sdf']) assert.equal(measureButtons(format).length, 0, format);
});

test('the resolved document can still withhold Measure from a STEP file', () => {
  assert.equal(measureButtons('step', false).length, 0);
  assert.equal(measureButtons('step', true).length, 1);
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
    assert.deepEqual(nodes.map(node => node.props.label).filter(Boolean), ['Measure', 'Draw']);
    assert.equal(nodes.some(node => node.props['aria-label'] === 'Zoom controls'), false);
    toolbar.unmount(); outer.unmount();
  }
});

test('fullscreen has no floating controls, even with an active tool', () => {
  const toolbar = render(FloatingToolBar, { selectedEntry: { file: 'part.step' }, previewMode: true, drawToolActive: true });
  assert.equal(toolbar.tree, null);
  toolbar.unmount();
});

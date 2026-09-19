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

test('interaction modes and view actions occupy two separate horizontal groups', () => {
  const outer = render(FloatingToolBar, {
    selectedEntry: { file: 'part.step' }, renderFormat: 'step', selectedMeshData: {},
    selectionFilter: 'all', onSelectionFilterChange() {}, handleSelectTabToolMode() {},
    handleScreenshotCopy() {},
  });
  const toolbar = render(outer.tree.type, outer.tree.props);
  const groups = elements(toolbar.tree).filter(node => node.props.role === 'group');
  const interaction = groups.find(node => node.props['aria-label'] === 'Interaction tools');
  const actions = groups.find(node => node.props['aria-label'] === 'View and actions');
  assert.ok(interaction);
  assert.ok(actions);
  assert.deepEqual(
    elements(interaction).map(node => node.props.label).filter(Boolean),
    ['Select', 'Pan', 'Measure', 'Draw']
  );
  assert.equal(elements(actions).some(node => node.props.label === 'View controls'), true);
  assert.equal(elements(actions).some(node => node.props.label === 'Capture'), true);
  assert.equal(elements(actions).some(node => node.props.label === 'Display'), false);
  assert.equal(elements(actions).some(node => String(node.props.label || '').startsWith('Viewing mode:')), false);
  assert.equal(elements(toolbar.tree).some(node => node.props['aria-label'] === 'Zoom controls'), false);
  toolbar.unmount(); outer.unmount();
});

test('Render keeps interaction tools and ordinary view actions available', () => {
  const outer = render(FloatingToolBar, {
    selectedEntry: { file: 'part.step' }, renderFormat: 'step', selectedMeshData: {},
    renderMode: true, selectionFilter: 'all', onSelectionFilterChange() {},
    handleSelectTabToolMode() {}, handleScreenshotCopy() {},
  });
  const toolbar = render(outer.tree.type, outer.tree.props);
  const labels = elements(toolbar.tree).map(node => node.props.label).filter(Boolean);
  for (const label of ['Select', 'Pan', 'Measure', 'Draw', 'View controls', 'Capture']) {
    assert.equal(labels.includes(label), true, label);
  }
  assert.equal(elements(toolbar.tree).some(node => node.type?.name === 'SelectionFilterMenu'), true);
  toolbar.unmount(); outer.unmount();
});

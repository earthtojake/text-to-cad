import assert from 'node:assert/strict';
import test from 'node:test';
import { buildPositionSection } from './MotionControlsSection.js';
import PoseControlsSection from './PoseControlsSection.js';
import { KinematicsPoseRow, MotionResetButton, NO_PRESET_VALUE } from '../../../kit/inspector/kinematicsControls.jsx';
import { FileSheetSliderField } from '../../../kit/inspector/FileSheet.js';
import { elements } from '../../../../../scripts/reactHarness.mjs';

const definition = { parameters: [{ id: 'hinge', label: 'Hinge', type: 'number' }],
  defaultParameterValues: { hinge: 0 }, manifest: { poses: { rest: { hinge: 0 } } } };

test('Position is poses and joints: without a pose runtime there is no section', () => {
  assert.equal(buildPositionSection(), null);
  for (const props of [{ poseRuntime: { definition } }, { poseRuntime: { error: 'Invalid joints' } }]) {
    const section = buildPositionSection(props);
    assert.equal(section.id, 'position');
    assert.equal(section.title, 'Position');
    assert.deepEqual(elements(section.content).filter(node => node.type === PoseControlsSection).length, 1);
  }
});

test('one global Reset calls the coordinated host command', () => {
  const calls = [];
  const pose = { definition, onResetMotion: () => calls.push('both'), onResetParameters: () => calls.push('wrong') };
  const section = buildPositionSection({ poseRuntime: pose });
  const controls = elements(section.content).find(node => node.type === PoseControlsSection);
  const header = elements(PoseControlsSection(controls.props)).find(node => node.type === KinematicsPoseRow);
  header.props.onReset();
  assert.deepEqual(calls, ['both']);
  assert.equal(elements(section.content).some(node => node.type === MotionResetButton), false, 'no separate bottom Reset');
});

test("the pose row and the joints are ONE section's rows, with no section of their own; either can exist alone", () => {
  const rows = def => elements(PoseControlsSection({ runtime: { definition: def } }));
  const kinds = def => rows(def).filter(node => [KinematicsPoseRow, FileSheetSliderField].includes(node.type)).map(node => node.type);
  assert.deepEqual(kinds(definition), [KinematicsPoseRow, FileSheetSliderField]);
  assert.deepEqual(kinds({ ...definition, parameters: [] }), [KinematicsPoseRow]);
  assert.deepEqual(kinds({ ...definition, manifest: {} }), [FileSheetSliderField]);
});

test('animation-owned authored values do not claim a named position, and parameters stay editable', () => {
  const onParameterChange = () => {};
  const content = PoseControlsSection({ runtime: { definition, parameterValues: { hinge: 0 }, positionActive: false, onParameterChange } });
  const nodes = elements(content);
  assert.equal(nodes.find(node => node.type === KinematicsPoseRow).props.activeValue, NO_PRESET_VALUE);
  assert.equal(nodes.find(node => node.type === FileSheetSliderField).props.disabled, undefined);
  assert.equal(nodes.some(node => node.props.title === 'Transition'), false);
});

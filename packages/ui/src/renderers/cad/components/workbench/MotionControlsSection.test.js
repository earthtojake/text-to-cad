import assert from 'node:assert/strict';
import test from 'node:test';
import { buildMotionControlsTab, MotionResetButton } from './MotionControlsSection.js';
import PoseControlsSection from './PoseControlsSection.js';
import { KinematicsPoseRow, NO_PRESET_VALUE } from './KinematicsControls.js';
import { FileSheetStaticSection, FileSheetSliderField } from './FileSheet.js';
import { elements } from '../../../../../scripts/reactHarness.mjs';

const definition = { parameters: [{ id: 'hinge', label: 'Hinge', type: 'number' }],
  defaultParameterValues: { hinge: 0 }, manifest: { poses: { rest: { hinge: 0 } } } };
const animation = { clips: [{ id: 'turn', duration: 3 }], activeClipId: 'turn' };

test('Kinematics is poses and joints: animation is the Animate tool, so routines alone make no tab', () => {
  assert.equal(buildMotionControlsTab(), null);
  for (const props of [{ animationRuntime: animation }, { animationRuntime: { status: 'loading' } }]) assert.equal(buildMotionControlsTab(props), null);
  for (const props of [{ poseRuntime: { definition } }, { poseRuntime: { error: 'Invalid joints' } }, { poseRuntime: { definition }, animationRuntime: animation }]) {
    const tab = buildMotionControlsTab(props);
    assert.equal(tab.id, 'kinematics');
    assert.equal(tab.title, 'Kinematics');
    assert.deepEqual(elements(tab.content).filter(node => node.type === PoseControlsSection).length, 1);
  }
});

test('one global Reset calls the coordinated host command', () => {
  const calls = [];
  const pose = { definition, onResetMotion: () => calls.push('both'), onResetParameters: () => calls.push('wrong') };
  const playback = { ...animation, resetModel: () => calls.push('wrong') };
  const tab = buildMotionControlsTab({ poseRuntime: pose, animationRuntime: playback });
  const children = elements(tab.content).filter(node => [PoseControlsSection, MotionResetButton].includes(node.type));
  assert.deepEqual(children.map(node => node.type), [PoseControlsSection, MotionResetButton]);
  const reset = MotionResetButton(children[1].props);
  elements(reset).find(node => node.props.onClick).props.onClick();
  assert.deepEqual(calls, ['both']);
  assert.equal(elements(PoseControlsSection({ runtime: pose })).some(node => node.props.onReset || node.props.onCopy || node.props.transition), false);
});

test('Pose and Joints are separate permanent sections; either can exist independently', () => {
  const titles = def => elements(PoseControlsSection({ runtime: { definition: def }, hideWhenEmpty: true }))
    .filter(node => node.type === FileSheetStaticSection).map(node => node.props.title);
  assert.deepEqual(titles(definition), ['Pose', 'Joints']);
  assert.deepEqual(titles({ ...definition, parameters: [] }), ['Pose']);
  assert.deepEqual(titles({ ...definition, manifest: {} }), ['Joints']);
});

test('animation-owned authored values do not claim a named position, and parameters stay editable', () => {
  const onParameterChange = () => {};
  const content = PoseControlsSection({ runtime: { definition, parameterValues: { hinge: 0 }, positionActive: false, onParameterChange } });
  const nodes = elements(content);
  assert.equal(nodes.find(node => node.type === KinematicsPoseRow).props.activeValue, NO_PRESET_VALUE);
  assert.equal(nodes.find(node => node.type === FileSheetSliderField).props.disabled, undefined);
  assert.equal(nodes.some(node => node.props.title === 'Transition'), false);
});

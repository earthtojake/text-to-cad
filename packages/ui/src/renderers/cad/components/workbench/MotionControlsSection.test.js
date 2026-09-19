import assert from 'node:assert/strict';
import test from 'node:test';
import { buildMotionControlsTab } from './MotionControlsSection.js';
import AnimationControlsSection from './AnimationControlsSection.js';
import PoseControlsSection from './PoseControlsSection.js';
import { KinematicsTransitionRows } from './KinematicsControls.js';
import { FileSheetSubsection } from './FileSheet.js';
import { elements } from '../../../../../scripts/reactHarness.mjs';

const definition = { parameters: [], defaultParameterValues: {}, manifest: { poses: { rest: {} } } };
const animation = { clips: [{ id: 'turn', duration: 3 }], activeClipId: 'turn' };

test('Motion is absent without controls and independently includes either system', () => {
  assert.equal(buildMotionControlsTab(), null);
  for (const props of [{ poseRuntime: { definition } }, { animationRuntime: animation }, { animationRuntime: { status: 'loading' } }, { poseRuntime: { error: 'Invalid joints' } }]) {
    const tab = buildMotionControlsTab(props);
    assert.equal(tab.id, 'motion');
    assert.equal(tab.title, 'Motion');
    assert.equal(elements(tab.content).filter(node => [AnimationControlsSection, PoseControlsSection].includes(node.type)).length, 1);
  }
});

test('Animation precedes Position while each retains its own runtime and actions', () => {
  const calls = [];
  const pose = { definition, onResetParameters: () => calls.push('position') };
  const playback = { ...animation, onRestart: () => calls.push('animation') };
  const tab = buildMotionControlsTab({ poseRuntime: pose, animationRuntime: playback });
  const children = elements(tab.content).filter(node => [AnimationControlsSection, PoseControlsSection].includes(node.type));
  assert.deepEqual(children.map(node => node.type), [AnimationControlsSection, PoseControlsSection]);
  assert.equal(children[0].props.runtime, playback);
  assert.equal(children[1].props.runtime, pose);
  const animationControls = AnimationControlsSection(children[0].props);
  elements(animationControls).find(node => node.props['aria-label'] === 'Restart animation').props.onClick();
  assert.deepEqual(calls, ['animation']);
  const positionControls = PoseControlsSection(children[1].props);
  elements(positionControls).find(node => node.props.onReset).props.onReset();
  assert.deepEqual(calls, ['animation', 'position']);
});

test('transition preferences live inside Position with no nested Transition section', () => {
  const transition = { animate: true, speed: 1 };
  const content = PoseControlsSection({ runtime: { definition, transition } });
  const position = elements(content).find(node => node.type === FileSheetSubsection);
  assert.equal(position.props.title, 'Position');
  const rows = elements(position).find(node => node.type === KinematicsTransitionRows);
  assert.equal(rows.props.transition, transition);
  assert.equal(elements(KinematicsTransitionRows(rows.props)).some(node => node.type === FileSheetSubsection), false);
  assert.equal(elements(content).filter(node => node.type === FileSheetSubsection).length, 1);
});

test('animation gate does not disable independent Position controls', () => {
  const tab = buildMotionControlsTab({ animationRuntime: { ...animation, enabled: false }, poseRuntime: { definition } });
  const children = elements(tab.content).filter(node => [AnimationControlsSection, PoseControlsSection].includes(node.type));
  const controls = elements(AnimationControlsSection(children[0].props));
  assert.equal(controls.find(node => node.props['aria-label'] === 'Restart animation').props.disabled, true);
  assert.equal(controls.find(node => node.props['aria-label'] === 'Play animation').props.disabled, undefined);
  assert.equal(children[1].props.runtime.definition, definition);
});

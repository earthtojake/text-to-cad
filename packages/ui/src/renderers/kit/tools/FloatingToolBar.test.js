import assert from 'node:assert/strict';
import test from 'node:test';
import FloatingToolBar from './FloatingToolBar.js';
import { render, elements } from '../../../../scripts/reactHarness.mjs';

const tool = (id, extra = {}) => ({ id, label: id.toUpperCase(), icon: null, onSelect() {}, ...extra });
const buttons = tree => elements(tree).filter(node => typeof node.props.label === 'string');

test('the strip draws the tools it is handed, in order, and knows none by name', () => {
  const view = render(FloatingToolBar, { tools: [tool('b', { active: true }), tool('a', { disabled: true })] });
  assert.deepEqual(buttons(view.tree).map(node => [node.props.label, node.props.active, node.props['aria-pressed'], node.props.disabled]),
    [['B', true, true, undefined], ['A', false, false, true]]);
  assert.deepEqual(elements(view.tree).filter(node => node.props.role === 'group').map(node => node.props['aria-label']), ['Interaction tools']);
  view.unmount();
});

test('every press reaches onSelect, and a press is all a tool is: no tool opens a menu from the strip', () => {
  const pressed = [];
  const view = render(FloatingToolBar, { tools: [
    tool('plain', { onSelect: () => pressed.push('plain') }),
    tool('active', { active: true, description: 'described', onSelect: () => pressed.push('active') }),
  ] });
  const [plain, active] = buttons(view.tree);
  plain.props.onClick();
  active.props.onClick();
  active.props.onClick();
  assert.deepEqual(pressed, ['plain', 'active', 'active'], 'a press on an active tool is the tool\'s too');
  assert.equal(active.props['aria-description'], 'described');
  assert.equal(elements(view.tree).some(node => node.props['data-tool-menu-corner'] !== undefined), false, 'no corner marker');
  assert.equal([plain, active].some(node => node.props.onPointerDown || node.props.onKeyDown), false);
  view.unmount();
});

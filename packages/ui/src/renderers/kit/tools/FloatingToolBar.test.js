import assert from 'node:assert/strict';
import test from 'node:test';
import FloatingToolBar from './FloatingToolBar.js';
import { render, elements } from '../../../../scripts/reactHarness.mjs';

const tool = (id, extra = {}) => ({ id, label: id.toUpperCase(), icon: null, onSelect() {}, ...extra });
const buttons = tree => elements(tree).filter(node => typeof node.props.label === 'string');

test('the strip draws the tools it is handed, in order, and knows none by name', () => {
  const view = render(FloatingToolBar, { tools: [tool('b', { active: true }), tool('a', { disabled: true })], position: { top: '14px' } });
  assert.deepEqual(buttons(view.tree).map(node => [node.props.label, node.props.active, node.props['aria-pressed'], node.props.disabled]),
    [['B', true, true, undefined], ['A', false, false, true]]);
  assert.deepEqual(elements(view.tree).filter(node => node.props.role === 'group').map(node => node.props['aria-label']), ['Interaction tools']);
  assert.deepEqual(elements(view.tree)[0].props.style, { top: '14px' });
  view.unmount();
});

test('every press reaches onSelect; a menu tool keeps its first press for itself', () => {
  const pressed = [];
  const Menu = () => null;
  const view = render(FloatingToolBar, { tools: [
    tool('plain', { onSelect: () => pressed.push('plain') }),
    tool('menu', { secondPressOpensMenu: true, description: 'again for the menu', onSelect: () => pressed.push('menu'),
      menu: trigger => ({ type: Menu, props: { trigger }, key: null }) }),
  ] });
  const [plain] = buttons(view.tree);
  assert.equal(plain.props.onPointerDown, undefined);
  plain.props.onClick();
  const trigger = elements(view.tree).find(node => node.type === Menu).props.trigger;
  assert.equal(trigger.props['aria-description'], 'again for the menu');
  let prevented = 0;
  trigger.props.onPointerDown({ preventDefault: () => { prevented += 1; } });
  trigger.props.onKeyDown({ key: 'ArrowDown', preventDefault: () => { prevented += 1; } });
  trigger.props.onKeyDown({ key: 'a', preventDefault: () => { prevented += 1; } });
  assert.equal(prevented, 2, 'until it is active, a press never opens the menu and the keyboard selects the tool');
  assert.deepEqual(pressed, ['plain', 'menu']);
  const corner = { target: { closest: () => ({}) }, preventDefault: () => { prevented += 1; } };
  trigger.props.onPointerDown(corner);
  trigger.props.onClick(corner);
  assert.equal(prevented, 4, 'an inactive corner selects only, blocking menu pointer-down and click');
  assert.deepEqual(pressed, ['plain', 'menu', 'menu'], 'a corner press activates once');

  view.unmount();
});

test('an active menu tool lets its presses through to the menu; sub-toolbars follow tool order', () => {
  const view = render(FloatingToolBar, { tools: [
    tool('first', { subToolbar: 'under-first' }),
    tool('second', { active: true, secondPressOpensMenu: true, subToolbar: 'under-second' }),
    tool('third'),
  ] });
  const second = buttons(view.tree)[1];
  let prevented = 0;
  second.props.onPointerDown({ preventDefault: () => { prevented += 1; } });
  second.props.onKeyDown({ key: 'Enter', preventDefault: () => { prevented += 1; } });
  assert.equal(prevented, 0);
  const text = [];
  const walk = node => { if (typeof node === 'string') text.push(node); else if (Array.isArray(node)) node.forEach(walk); else if (node?.props) walk(node.props.children); };
  walk(view.tree);
  assert.deepEqual(text, ['under-first', 'under-second']);
  view.unmount();
});

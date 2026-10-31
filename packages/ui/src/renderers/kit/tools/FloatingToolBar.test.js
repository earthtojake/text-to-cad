import assert from 'node:assert/strict';
import test from 'node:test';
import FloatingToolBar, { touchStripFit } from './FloatingToolBar.js';
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

const rules = tools => {
  const view = render(FloatingToolBar, { tools, views: [{ id: 'display', label: 'Display', icon: null, tile: null }] });
  const row = elements(view.tree).filter(node => node.props['data-strip-rule'] === '' || typeof node.props.label === 'string' || node.props['data-view-controls'] === '')
    .map(node => (node.props['data-strip-rule'] === '' ? '|' : node.props['data-view-controls'] === '' ? 'VIEW' : node.props.label));
  view.unmount();
  return row;
};

test('one thin rule parts the strip\'s two sections: the tools that pick, then the model\'s effects with the view\'s controls after them, no rule between', () => {
  assert.deepEqual(rules([tool('select'), tool('pencil'), tool('shapes'), tool('measure'), tool('explode', { group: 'model' }), tool('clip', { group: 'model' })]),
    ['SELECT', 'PENCIL', 'SHAPES', 'MEASURE', '|', 'EXPLODE', 'CLIP', 'VIEW']);
});

test('with one group of tools only, the view\'s controls are the second section, after a rule', () => {
  assert.deepEqual(rules([tool('select'), tool('pencil'), tool('shapes'), tool('measure')]), ['SELECT', 'PENCIL', 'SHAPES', 'MEASURE', '|', 'VIEW']);
});

test('a tool with a menu is one control: its button and chevron under one fill, lit while the tool is in hand', () => {
  const view = render(FloatingToolBar, { tools: [tool('select', { active: true, menu: 'MENU' }), tool('measure', { menu: 'MENU' }), tool('pencil')] });
  const splits = elements(view.tree).filter(node => node.props['data-tool-split'] === '');
  assert.deepEqual(splits.map(node => node.props['data-active']), ['', undefined], 'the pair, lit with the tool in hand');
  assert.ok(splits.every(node => /group\/split/.test(node.props.className)), 'one hover for the pair');
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
  assert.equal([plain, active].some(node => node.props.onPointerDown || node.props.onKeyDown), false);
  view.unmount();
});

test('a phone\'s strip keeps its 36px tiles in one row and hands what does not fit, from its end, to More', () => {
  // A STEP's strip: Select with its filter's chevron, five more tools, then Display and Preview (a host with no navbar).
  const entries = [{ width: 56, view: false }, ...Array(5).fill({ width: 36, view: false }), { width: 36, view: true }, { width: 36, view: true }];
  // A 375px phone (the column 359px): everything fits, no More.
  assert.equal(touchStripFit(entries, 359), 8);
  // A 320px phone (304px): Select and the next three tools, then More (the last tool, Display, Preview).
  assert.equal(touchStripFit(entries, 304), 5);
  // Narrower still: fewer tools before More.
  assert.equal(touchStripFit(entries, 200), 3);
});

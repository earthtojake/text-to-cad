import assert from 'node:assert/strict';
import test from 'node:test';

import { promptView, promptViews, sameView } from './views.js';

/** A prompt's views: the view on screen and those the annotation was drawn in, as snapshot jobs say them. */

const camera = (overrides = {}) => ({ position: [0, -100, 0], target: [0, 0, 0], up: [0, 0, 1], orthographicHalfHeight: 50, ...overrides });
const view = (overrides = {}) => ({ camera: camera(), width: 1600, height: 1200, ...overrides });
// The camera turned `degrees` about the up axis.
const turned = degrees => {
  const radians = degrees * Math.PI / 180;
  return camera({ position: [100 * Math.sin(radians), -100 * Math.cos(radians), 0] });
};

test("a view is the viewer's camera at the prompt's size, its mode and Grid switch, and what places or hides the parts", () => {
  const made = promptView({ camera: camera(), width: 800, height: 600 }, {
    display: { mode: 'xray', grid: true, appearance: 'dark', camera: { projection: 'perspective' },
      clip: { enabled: true, axis: 'x', at: 2, invert: false }, exploded: { enabled: false, amount: 0.5 } },
    state: { kinematics: { elbow: 30 }, jointValues: {}, hide: ['o1.2'], focus: [] },
  });
  assert.deepEqual(made, {
    camera: camera(), width: 1600, height: 1200,
    display: { mode: 'xray', grid: true, clip: { enabled: true, axis: 'x', at: 2, invert: false } },
    kinematics: { elbow: 30 },
    selection: { hide: ['o1.2'] },
  });
  assert.equal(promptView(null), null);
  // Explode is the view's where it spreads the parts, never on at no amount.
  const spread = amount => promptView({ camera: camera(), width: 800, height: 600 }, { display: { exploded: { enabled: true, amount } } }).display;
  assert.deepEqual([spread(0), spread(0.5)], [undefined, { exploded: { enabled: true, amount: 0.5 } }]);
  // The grid says off too: a snapshot replays the view exactly. A drawing has no mode, and says none.
  assert.deepEqual(promptView({ camera: camera(), width: 800, height: 600 }, { display: { mode: 'parts' } }).display, { mode: 'parts', grid: false });
  assert.ok(!sameView(view({ display: { mode: 'solid', grid: false } }), view({ display: { mode: 'solid', grid: true } })));
  assert.ok(!sameView(view({ display: { mode: 'solid', grid: false } }), view({ display: { mode: 'shaded', grid: false } })));
  // Parts named by refs are hidden and isolated in the view's display, as `--display` takes them.
  const refs = { hidden: ['/w/kit.xbf#lid'], isolated: ['/w/kit.xbf#hand'] };
  const hiding = promptView({ camera: camera(), width: 800, height: 600 }, { display: { mode: 'solid' }, state: refs });
  assert.deepEqual(hiding.display, { mode: 'solid', grid: false, ...refs });
  assert.equal(promptView({ camera: camera(), width: 800, height: 600 }, { state: { hidden: [], isolated: [] } }).display, undefined);
  assert.ok(!sameView(view({ display: { mode: 'solid', grid: false } }), view({ display: hiding.display })));
});

test("PMI the person turned off is off in the view, as `cadgen snapshot --display` takes it", () => {
  const view = state => promptView({ camera: camera(), width: 800, height: 600 }, { display: { mode: 'solid' }, state });
  assert.deepEqual(view({ pmi: false }).display, { mode: 'solid', grid: false, pmi: false });
  // Shown, as a snapshot draws it by default: nothing to say.
  assert.deepEqual(view({ pmi: true }).display, { mode: 'solid', grid: false });
  assert.deepEqual(view({}).display, { mode: 'solid', grid: false });
});

test("a routine's kept frame is the view's animation, a snapshot job's {clip, time}", () => {
  const made = promptView({ camera: camera(), width: 800, height: 600 }, { state: { animation: { clip: 'swing', time: 1.5 } } });
  assert.deepEqual(made.animation, { clip: 'swing', time: 1.5 });
  assert.equal(promptView({ camera: camera(), width: 800, height: 600 }, { state: { animation: null } }).animation, undefined);
  assert.ok(sameView(view({ animation: { clip: 'swing', time: 1.5 } }), view({ animation: { clip: 'swing', time: 1.5 } })));
  assert.ok(!sameView(view(), view({ animation: { clip: 'swing', time: 1.5 } })));
  assert.ok(!sameView(view({ animation: { clip: 'swing', time: 1 } }), view({ animation: { clip: 'swing', time: 1.5 } })));
});

test('a camera nudged less than 2°, zoomed or panned less than 5% is the same view; more, or any other change, is another', () => {
  assert.ok(sameView(view(), view({ camera: turned(1.5) })));
  assert.ok(!sameView(view(), view({ camera: turned(3) })));
  assert.ok(sameView(view(), view({ camera: camera({ orthographicHalfHeight: 52 }) })));
  assert.ok(!sameView(view(), view({ camera: camera({ orthographicHalfHeight: 60 }) })));
  assert.ok(sameView(view(), view({ camera: camera({ target: [3, 0, 0], position: [3, -100, 0] }) })));
  assert.ok(!sameView(view(), view({ camera: camera({ target: [8, 0, 0], position: [8, -100, 0] }) })));
  assert.ok(!sameView(view(), view({ display: { exploded: { enabled: true, amount: 1 } } })));
  assert.ok(!sameView(view(), view({ selection: { hide: ['o1.2'] } })));
});

test('every prompt carries the exact current view, reusing a matching ink view or appending it', () => {
  const drawn = [{ ...view(), label: 'view 1' }, { ...view({ camera: turned(90) }), label: 'view 2' }, { ...view({ camera: turned(180) }), label: 'view 3' }];
  const ink = [{ view: 'view 1' }, { view: 'view 3' }];
  const current = view({ camera: turned(1), width: 1200, height: 1600 });
  const merged = promptViews(current, drawn, ink);
  assert.deepEqual(merged, [{ ...current, label: 'view 1' }, drawn[2]]);
  assert.equal(drawn[0].width, 1600, 'the stored annotation view stays unchanged');
  const moved = view({ camera: turned(45) });
  assert.deepEqual(promptViews(moved, drawn, ink), [drawn[0], drawn[2], { ...moved, label: 'current view' }]);
  assert.deepEqual(promptViews(current, drawn, []), [{ ...current, label: 'current view' }], 'selection/text/measurements alone still have a view');
  assert.deepEqual(promptViews(current, [], [{}]), [{ ...current, label: 'current view' }]);
  assert.deepEqual(promptViews(null, drawn, ink), [drawn[0], drawn[2]]);
});

test('a prompt view retains the captured projection and lens, and groups different lenses separately', () => {
  const captured = { camera: camera(), display: { camera: { projection: 'perspective', focalLength: 85 } }, width: 800, height: 600 };
  const made = promptView(captured, { display: { mode: 'solid', grid: false } });
  assert.deepEqual(made.display.camera, captured.display.camera);
  assert.ok(!sameView(made, { ...made, display: { ...made.display, camera: { projection: 'orthographic' } } }));
  assert.ok(!sameView(made, { ...made, display: { ...made.display, camera: { projection: 'perspective', focalLength: 50 } } }));
});

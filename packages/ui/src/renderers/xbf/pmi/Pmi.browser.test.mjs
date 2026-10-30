import assert from 'node:assert/strict';
import { test } from 'node:test';
import { PNG } from 'pngjs';
import { serveXbfHarness } from '../../harness/xbfScenario.mjs';

// An engine document's PMI in a real browser, over core's bracket (a 40 x 20 x 4 plate on
// z = -2..2 with a Ø8 hole at the origin) served carrying PMI as `cadgen.engine.pmi` serves it: a
// datum on the bottom, the thickness toleranced and placed in code, a flatness on the top, each of
// the plate (its part, the structure's first prototype). Its
// callouts are drawn on the model and stay put on it, a fixed size, as the camera moves; a pick of
// one lights its face; it hides and shows, kept across a reopen, and goes with its part hidden; a
// named view picked moves the camera, cuts the part and draws its PMI alone, and leaves cleanly; a
// value edited, a label moved and a new annotation each go to Quick Edit as the call the model's
// code should make; and a rebuild that loses a reference says so, where the code placed it.

const TOP = 'plate/f:bracket.fillet1~d3f70920d846';
const BOTTOM = 'plate/f:bracket.fillet1~908aee34f872';
const ref = (role, at) => ({ role, ref: at, written: at, status: 'ok', candidates: null });
const PMI = [
  { id: 'A', kind: 'datum', label: null, status: 'ok', problem: null, part: 0, refs: [ref('feature', BOTTOM)], datum: { letter: 'A' }, presentation: null, xcaf_type: null },
  { id: 'thickness', kind: 'dimension', label: null, status: 'ok', problem: null, part: 0, refs: [ref('from', BOTTOM), ref('to', TOP)],
    dimension: { type: 'distance', nominal: { value: 4, unit: 'mm', source: 'geometry' }, tolerance: { type: 'plus_minus', upper: 0.2, lower: -0.2 } },
    presentation: { anchor: [20, -10, -2], offset: [8, -6, 2] }, xcaf_type: null },
  { id: 'top-flat', kind: 'geometric_tolerance', label: null, status: 'ok', problem: null, part: 0, refs: [ref('feature', TOP)],
    geometric_tolerance: { characteristic: 'flatness', value: 0.05, unit: 'mm', zone: null, modifier: null, datums: [] }, presentation: null, xcaf_type: null },
];
const withPmi = structure => ({ ...structure, pmi: structure.pmi || PMI });

const unit = v => { const length = Math.hypot(...v); return v.map(c => c / length); };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

async function openBracket(t, options = { edit: withPmi }) {
  const harness = await serveXbfHarness(t, options);
  const opened = await harness.open();
  const { page, pane } = opened;
  const controller = 'window.cadHarness.a.controller';
  const loaded = () => page.waitForFunction(`${controller}?.readState().loading === false`);
  await loaded();
  const canvas = pane.locator('canvas').first();
  const label = id => pane.locator(`[data-pmi-label="${id}"]`);
  // Every label of the PMI drawn, laid out where the camera puts it.
  const drawn = () => page.waitForFunction(() => {
    const labels = [...document.querySelectorAll('[data-pmi-label]')];
    return labels.length && labels.every(element => element.style.visibility !== 'hidden' && element.style.transform);
  });
  const labels = () => pane.locator('[data-pmi-label]').evaluateAll(elements => elements.map(element => element.getAttribute('data-pmi-label')));
  // A camera set from outside, orthographic; where a model point falls on screen under it.
  const view = async (camera) => {
    await page.evaluate(`${controller}.setCamera(${JSON.stringify({ ...camera, projection: 'orthographic' })})`);
    const box = await canvas.boundingBox();
    const live = await page.evaluate(() => window.__cadCamera());
    const forward = unit(live.target.map((value, axis) => value - live.position[axis]));
    const right = unit(cross(forward, live.up)), up = cross(right, forward);
    const scale = box.height / (2 * live.halfHeight / live.zoom);
    return point => {
      const offset = point.map((value, axis) => value - live.target[axis]);
      return { x: box.x + box.width / 2 + dot(offset, right) * scale, y: box.y + box.height / 2 - dot(offset, up) * scale };
    };
  };
  // The viewport's own pixels, without any chrome over them.
  const capture = async () => {
    const base64 = await page.evaluate(async () => {
      const data = new Uint8Array(await (await window.cadHarness.a.controller.capture()).arrayBuffer());
      let binary = ''; for (const byte of data) binary += String.fromCharCode(byte);
      return btoa(binary);
    });
    return PNG.sync.read(Buffer.from(base64, 'base64')).data;
  };
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const center = async locator => { const box = await locator.boundingBox(); return { x: box.x + box.width / 2, y: box.y + box.height / 2, box }; };
  // What Quick Edit hands the agent: its prompt, copied.
  const prompt = async () => {
    const count = await page.evaluate(() => window.cadHarness.promptMessages.length);
    await pane.getByRole('button', { name: 'Copy Prompt', exact: true }).click();
    await page.waitForFunction(seen => window.cadHarness.promptMessages.length > seen || document.querySelector('[data-quick-edit-box] [role=alert]'), count);
    const alert = await pane.locator('[data-quick-edit-box] [role=alert]').allInnerTexts();
    assert.deepEqual(alert, [], 'the prompt was copied');
    return page.evaluate(() => window.cadHarness.promptMessages.at(-1));
  };
  return { ...harness, ...opened, loaded, label, drawn, labels, view, capture, settle, center, controller, prompt };
}

test('PMI is drawn on the model and stays legible as the camera moves; a pick lights its face; it hides, and stays hidden across a reopen; a named view applies and leaves', async (t) => {
  const { page, pane, errors, label, drawn, labels, view, capture, settle, center, loaded, update, controller, prompt } = await openBracket(t);
  await view({ position: [60, -80, 70], target: [0, 0, 2], up: [0, 0, 1], orthographicHalfHeight: 30 });
  await drawn();
  assert.deepEqual(await labels(), ['A', 'thickness', 'top-flat']);
  // Each says what the document says: the datum's letter, the thickness with its tolerance, the frame.
  assert.equal(await label('A').getAttribute('aria-label'), 'Datum A');
  assert.equal(await label('thickness').getAttribute('aria-label'), '4.0 ±0.2');
  assert.equal(await label('top-flat').getAttribute('aria-label'), 'Flatness 0.05');

  // A turn and a zoom of the camera carry every label with the model, at the same size on screen.
  const before = await center(label('top-flat'));
  await view({ position: [-70, -60, 60], target: [0, 0, 2], up: [0, 0, 1], orthographicHalfHeight: 15 });
  await settle();
  const after = await center(label('top-flat'));
  assert.ok(Math.hypot(after.x - before.x, after.y - before.y) > 10, 'the label moved with the model');
  assert.ok(Math.abs(after.box.width - before.box.width) < 1 && Math.abs(after.box.height - before.box.height) < 1, 'at the size it was');
  const canvasBox = await pane.locator('canvas').first().boundingBox();
  assert.ok(after.x > canvasBox.x && after.x < canvasBox.x + canvasBox.width && after.y > canvasBox.y && after.y < canvasBox.y + canvasBox.height, 'on screen');

  // A pick of the flatness lights the top it is of; Escape lets go, and the view is as it was.
  await view({ position: [60, -80, 70], target: [0, 0, 2], up: [0, 0, 1], orthographicHalfHeight: 30 });
  await settle();
  const still = await capture();
  await label('top-flat').click();
  await page.waitForFunction(() => document.querySelector('[data-pmi-label="top-flat"]')?.getAttribute('aria-pressed') === 'true');
  await settle();
  assert.ok(!(await capture()).equals(still), 'its face is lit');
  // Its values read in the PMI section, with their units and where each came from.
  await pane.getByRole('button', { name: 'PMI', exact: true }).click();
  const details = pane.locator('[data-pmi-details="top-flat"]');
  await details.waitFor();
  assert.match(await details.innerText(), /Kind\s*Flatness/);
  assert.match(await details.innerText(), /Feature\s*plate · face 2/);
  assert.match(await details.innerText(), /Placed\s*Beside its feature/);
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelector('[data-pmi-label="top-flat"]')?.getAttribute('aria-pressed') === 'false');
  await settle();
  assert.ok((await capture()).equals(still), 'nothing is lit once it is let go');

  // One hidden by its row's eye, then all of them by the section's.
  await pane.locator('[data-pmi-visibility="top-flat"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-pmi-label="top-flat"]'));
  assert.deepEqual(await labels(), ['A', 'thickness']);
  await pane.getByRole('button', { name: 'Hide PMI', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('[data-pmi-label]'));
  // The view goes and comes back over the same record: what was hidden is hidden still.
  await page.evaluate(() => window.cadHarness.mounted(false));
  await page.evaluate(() => window.cadHarness.mounted(true));
  await loaded();
  await pane.getByRole('button', { name: 'PMI', exact: true }).click();
  await pane.getByRole('button', { name: 'Reveal PMI', exact: true }).click();
  await drawn();
  assert.deepEqual(await labels(), ['A', 'thickness']);
  // Its part hidden in the Model tree, its callouts go with it; shown again, they come back.
  await pane.getByRole('button', { name: 'Model tree', exact: true }).click();
  await pane.getByRole('button', { name: 'Hide plate', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('[data-pmi-label]'));
  await pane.getByRole('button', { name: 'Reveal plate', exact: true }).click();
  await drawn();
  assert.deepEqual(await labels(), ['A', 'thickness']);

  // The engine's plate as a model-based definition (`pmi_plate/v4`), its part placed 30 along y: the
  // section reads it as a drawing is read, its views, notes, coverage and annotations. View A-A
  // picked is seen from the front, cut across y where its section is in the part's frame (0 there,
  // 30 here), keeping the far side, and draws only the four callouts it shows; picked again, the
  // camera, the Clip and the PMI are as they were.
  await update('pmi_plate/v4', structure => ({ ...structure, instances: structure.instances.map(instance => ({ ...instance, matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 30, 0, 1] })) }));
  await loaded();
  await view({ position: [120, -130, 140], target: [0, 30, 0], up: [0, 0, 1], orthographicHalfHeight: 70 });
  await drawn();
  const every = ['A', 'thickness', 'hole-diameter', 'hole-from-front', 'hole-from-left', 'top-flatness', 'hole-position', 'hole-profile', 'mask'];
  assert.deepEqual(await labels(), every);
  // Limits stacked in words as in the box; the flag note its flag and its number.
  assert.equal(await label('thickness').getAttribute('aria-label'), '9.8\u201310.2');
  assert.equal(await label('mask').innerText(), '3');
  await pane.getByRole('button', { name: 'PMI', exact: true }).click();
  assert.deepEqual(await pane.locator('[data-tool-panel-id="pmi"] h2').allInnerTexts(), ['Views', 'Notes', 'Coverage', 'Annotations']);
  const read = () => page.evaluate(`({ state: ${controller}.readState(), camera: window.__cadCamera(), cut: window.__cadStage().cut })`);
  const unpicked = await read();
  const section = pane.getByRole('button', { name: 'A-A', exact: true });
  await section.click();
  await page.waitForFunction(() => [...document.querySelectorAll('[data-pmi-label]')].map(element => element.dataset.pmiLabel).join() === 'hole-diameter,hole-position,hole-profile,mask'
    && window.__cadStage().cut === 1);
  const seen = await read();
  assert.deepEqual(seen.state.display.clip, { enabled: true, axis: 'y', at: 30, invert: true, partColors: true });
  assert.equal(seen.cut, 1);
  const toEye = unit(seen.camera.position.map((value, axis) => value - seen.camera.target[axis]));
  assert.ok(Math.hypot(toEye[0], toEye[1] + 1, toEye[2]) < 1e-6, `seen from the front: ${toEye}`);
  assert.ok(Math.hypot(seen.camera.target[0], seen.camera.target[1] - 30, seen.camera.target[2]) < 1e-6, `at the part where it stands: ${seen.camera.target}`);
  await drawn();
  // Viewed from here, it is A-A again: the viewport's camera and the Clip taken back into the
  // part's frame (the cut at y 30 here is y 0 there), showing the four it draws.
  await pane.getByRole('button', { name: 'New PMI', exact: true }).click();
  await page.locator('[data-pmi-new-kind="view"]').click();
  await pane.locator('[data-pmi-new="view"] [data-pmi-add]').click();
  await pane.getByRole('button', { name: 'Add view', exact: true }).waitFor();
  const asked = await prompt();
  assert.ok(asked.includes('\nview("view", camera=camera((0, -1, 0), (0, 0, 1)), shows=["hole-diameter", "hole-position", "hole-profile", "mask"], '
    + 'section=section("y", 0, invert=True))\n'), asked);
  await pane.getByRole('button', { name: 'Close Quick Edit', exact: true }).click();
  await section.click();
  await page.waitForFunction(count => document.querySelectorAll('[data-pmi-label]').length === count && window.__cadStage().cut === 0, every.length);
  const left = await read();
  assert.deepEqual([left.state.display.clip, left.cut], [unpicked.state.display.clip, unpicked.cut]);
  for (const key of ['position', 'target', 'up']) {
    assert.ok(Math.hypot(...left.camera[key].map((value, axis) => value - unpicked.camera[key][axis])) < 1e-6, `the camera's ${key} as it was`);
  }
  assert.deepEqual(errors, []);
});

test('a change to PMI goes to Quick Edit as the code it asks for, and a rebuild that loses a reference says so where the code placed it', async (t) => {
  const { page, pane, errors, label, drawn, view, settle, center, update, prompt } = await openBracket(t);
  await view({ position: [60, -80, 70], target: [0, 0, 2], up: [0, 0, 1], orthographicHalfHeight: 30 });
  await drawn();

  // A drag of a label not picked moves nothing; picked, it moves, and Quick Edit asks for the placement.
  const at = await center(label('top-flat'));
  await page.mouse.move(at.x, at.y); await page.mouse.down(); await page.mouse.move(at.x + 60, at.y + 30, { steps: 4 }); await page.mouse.up();
  await settle();
  assert.equal(await pane.locator('[data-quick-edit-box]').count(), 0, 'a drag of an unpicked label asks for nothing');
  await label('top-flat').click();
  const picked = await center(label('top-flat'));
  await page.mouse.move(picked.x, picked.y); await page.mouse.down(); await page.mouse.move(picked.x + 60, picked.y + 30, { steps: 4 }); await page.mouse.up();
  await pane.getByRole('button', { name: 'Move top-flat', exact: true }).waitFor();
  const moved = await center(label('top-flat'));
  assert.ok(Math.hypot(moved.x - picked.x - 60, moved.y - picked.y - 30) < 3, 'it stands where it was let go');
  let text = await prompt();
  assert.match(text, /Move the PMI "top-flat"[^\n]*placement only/);
  assert.ok(text.includes(`flatness_tolerance("top-flat", "${TOP}", 0.05, presentation=place(anchor=(`), text);

  // A tolerance edited in the section: the call, its references as the code wrote them, the new tolerance.
  await pane.getByRole('button', { name: 'PMI', exact: true }).click();
  await pane.locator('[data-pmi-pick="thickness"]').click();
  const tolerance = pane.locator('[data-pmi-details="thickness"]').getByRole('textbox', { name: 'Tolerance' });
  await tolerance.click(); await tolerance.fill('+0.1/-0.05'); await tolerance.press('Enter');
  await pane.getByRole('button', { name: 'Change thickness', exact: true }).waitFor();
  text = await prompt();
  assert.ok(text.includes(`dimensional_location("thickness", "${BOTTOM}", "${TOP}", tolerance=plus_minus_tolerance(0.1, -0.05), presentation=place(anchor=(20, -10, -2), offset=(8, -6, 2)))`), text);
  // What the document says is unchanged until the code is: the label still says the document's tolerance.
  assert.equal(await label('thickness').getAttribute('aria-label'), '4.0 ±0.2');

  // A new annotation, of a face picked: the bottom, as a second datum would be. The menu says why
  // a kind the pick cannot make is off.
  await pane.getByRole('button', { name: 'Close Quick Edit', exact: true }).click();
  await pane.locator('[data-select-filter-trigger]').click();
  const filter = page.locator('[role=menu][aria-label="Selection filter"]');
  await filter.locator('[data-select-filter="faces"]').click();
  await filter.waitFor({ state: 'detached' });
  const under = await view({ position: [0, 0, -100], target: [0, 0, 0], up: [0, 1, 0], orthographicHalfHeight: 20 });
  const bottom = under([10, 6, -2]);
  await page.mouse.click(bottom.x, bottom.y);
  await pane.locator('[data-quick-edit-ref]').first().waitFor();
  assert.deepEqual(await pane.locator('[data-quick-edit-ref]').allInnerTexts(), ['plate\n5'], 'the bottom, face 5 of the plate, is picked');
  await pane.getByRole('button', { name: 'New PMI', exact: true }).click();
  assert.equal(await page.locator('[data-pmi-new-kind="distance"]').getAttribute('data-disabled'), '');
  await page.locator('[data-pmi-new-kind="flatness"]').click();
  const value = pane.locator('[data-pmi-new="flatness"]').getByRole('textbox', { name: 'Tolerance' });
  await value.click(); await value.fill('0.02'); await value.press('Enter');
  await pane.locator('[data-pmi-add]').click();
  await pane.getByRole('button', { name: 'Add flatness', exact: true }).waitFor();
  text = await prompt();
  assert.ok(text.includes(`Add this PMI to the annotate(...) call of the model's part "plate" (from cadgen.ap242 import annotate, flatness_tolerance):\nflatness_tolerance("flatness", "${BOTTOM}", 0.02)`), text);

  // The model rebuilt without the top's name: the flatness names nothing now. It is drawn where the
  // code placed it, broken, and its row says why; an annotation the viewer does not draw is listed,
  // saying why in the engine's words.
  await pane.getByRole('button', { name: 'Close Quick Edit', exact: true }).click();
  await view({ position: [60, -80, 70], target: [0, 0, 2], up: [0, 0, 1], orthographicHalfHeight: 30 });
  await update(structure => ({ ...structure, pmi: [...PMI.slice(0, 2), {
    ...PMI[2], status: 'missing', problem: `${TOP} names nothing in this build`, presentation: { anchor: [0, 6, 2], offset: [0, 0, 10] },
    refs: [{ role: 'feature', ref: TOP, written: TOP, status: 'missing', candidates: null }] },
  { id: 'profile', kind: 'unsupported', label: null, status: 'ok', problem: null, part: 0, refs: [], presentation: null,
    xcaf_type: 'XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface', reason: 'profile of surface is not a characteristic this holds', values: {} }] }));
  await page.waitForFunction(() => document.querySelector('[data-pmi-label="top-flat"]')?.getAttribute('data-pmi-status') === 'missing');
  await drawn();
  assert.equal(await label('profile').count(), 0, 'what the viewer does not draw is not drawn');
  await pane.locator('[data-pmi-pick="top-flat"]').click();
  assert.match(await pane.locator('[data-pmi-details="top-flat"]').innerText(), /names nothing in this build/);
  assert.match(await pane.locator('[data-pmi-row="profile"]').innerText(), /not shown/);
  await pane.locator('[data-pmi-pick="profile"]').click();
  assert.match(await pane.locator('[data-pmi-details="profile"]').innerText(), /Not shown: profile of surface is not a characteristic this holds\./);
  assert.deepEqual(errors, []);
});

// The engine's own: a plate built with `cadgen.ap242`'s calls (`annotate`, its faces named by the
// engine's element names), served as the engine served it (`pmi_plate/v1`), then rebuilt twice: 10
// mm thick with a Ø10 hole, located by basic distances from the front and the left side to its axis,
// then 12 mm with a Ø12 hole (every name kept: the same annotations, measured anew), then with a
// square cut where the hole was (the hole's name now on a flat face, where a diameter, a position
// and the basic from the front, square to it, cannot stand, and the basic from the left, parallel
// to it, measures to it as it now is).
test('PMI the engine built follows the model through edits: nominals measured anew, and a reference that can no longer stand marked', async (t) => {
  const { page, pane, errors, label, drawn, labels, view, settle, capture, update, loaded } = await openBracket(t, { fixture: 'pmi_plate/v1' });
  await view({ position: [120, -160, 140], target: [0, 0, 0], up: [0, 0, 1], orthographicHalfHeight: 60 });
  await drawn();
  assert.deepEqual(await labels(), ['A', 'thickness', 'hole-diameter', 'hole-from-front', 'hole-from-left', 'top-flatness', 'hole-position']);
  assert.equal(await label('thickness').getAttribute('aria-label'), '10.0 ±0.2');
  // Exact: its number boxed, no tolerance.
  assert.equal(await label('hole-from-front').getAttribute('aria-label'), '30 basic');
  assert.equal(await label('hole-from-front').locator('[data-pmi-basic]').innerText(), '30');
  assert.equal(await label('hole-diameter').getAttribute('aria-label'), '\u230010.0 +0.1/0');
  assert.equal(await label('hole-position').getAttribute('aria-label'), 'Position \u23000.1 | A');
  const still = await capture();
  await label('hole-diameter').click();
  await settle();
  assert.ok(!(await capture()).equals(still), 'the hole is lit');

  // Thicker, the hole bigger: the same annotations, still on their faces, measured anew; still picked.
  await update('pmi_plate/v2');
  await page.waitForFunction(() => document.querySelector('[data-pmi-label="thickness"]')?.getAttribute('aria-label') === '12.0 ±0.2');
  assert.equal(await label('hole-diameter').getAttribute('aria-label'), '\u230012.0 +0.1/0');
  assert.equal(await label('hole-diameter').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(await pane.locator('[data-pmi-label]').evaluateAll(elements => elements.map(element => element.dataset.pmiStatus)), ['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok']);

  // A square cut where the hole was: its name is a flat face's now, which a diameter, a position
  // and a distance from a face square to it cannot stand on.
  await update('pmi_plate/v3');
  await page.waitForFunction(() => document.querySelector('[data-pmi-label="hole-diameter"]')?.dataset.pmiStatus === 'invalid');
  assert.equal(await label('hole-position').getAttribute('data-pmi-status'), 'invalid');
  assert.equal(await label('thickness').getAttribute('data-pmi-status'), 'ok');
  assert.equal(await label('hole-from-front').getAttribute('data-pmi-status'), 'invalid');
  // A distance from a parallel face stands on the cut's flat face: measured to it as it now is.
  assert.equal(await label('hole-from-left').getAttribute('data-pmi-status'), 'ok');
  assert.equal(await label('hole-from-left').getAttribute('aria-label'), '44 basic');
  // Drawn where the code placed it, its nominal unknown; its row says what the engine said. Still
  // its part's, linked to no geometry, it is still the one picked.
  assert.equal(await label('hole-diameter').getAttribute('aria-label'), '\u2300? +0.1/0: f:edit_plate.cut.1;M:edit_plate.body is a plane face; a diameter is on a cylinder face');
  assert.equal(await label('hole-diameter').getAttribute('aria-pressed'), 'true');
  await pane.getByRole('button', { name: 'PMI', exact: true }).click();
  assert.match(await pane.locator('[data-pmi-details="hole-diameter"]').innerText(), /is a plane face; a diameter is on a cylinder face/);

  // Reopened, the document says the same: its PMI is the file's, not the view's.
  await page.evaluate(() => window.cadHarness.mounted(false));
  await page.evaluate(() => window.cadHarness.mounted(true));
  await loaded();
  await drawn();
  assert.deepEqual(await labels(), ['A', 'thickness', 'hole-diameter', 'hole-from-front', 'hole-from-left', 'top-flatness', 'hole-position']);
  assert.equal(await label('hole-diameter').getAttribute('data-pmi-status'), 'invalid');
  assert.deepEqual(errors, []);
});

// A document with no PMI has no PMI tile. A face's menu offers what it can carry, and a choice
// opens the PMI section on that kind's form, the face picked: the first annotation is made there.
test('a file with no PMI has no tile for it, and a face\'s menu starts the first one', async (t) => {
  const { page, pane, errors, view, loaded } = await openBracket(t, { fixture: 'bracket' });
  await loaded();
  assert.equal(await pane.getByRole('button', { name: 'PMI', exact: true }).count(), 0, 'no tile while there is no PMI');
  await pane.locator('[data-select-filter-trigger]').click();
  const filter = page.locator('[role=menu][aria-label="Selection filter"]');
  await filter.locator('[data-select-filter="faces"]').click();
  await filter.waitFor({ state: 'detached' });
  const down = await view({ position: [0, 0, 100], target: [0, 0, 0], up: [0, 1, 0], orthographicHalfHeight: 20 });
  const top = down([10, 6, 2]);
  await page.mouse.click(top.x, top.y, { button: 'right' });
  const menu = page.getByRole('menu');
  await menu.waitFor();
  assert.deepEqual(await menu.getByRole('menuitem').filter({ hasText: /^Add / }).allInnerTexts(), ['Add datum', 'Add flatness', 'Add surface profile', 'Add note']);
  await menu.getByRole('menuitem', { name: 'Add flatness', exact: true }).click();
  const form = pane.locator('[data-pmi-new="flatness"]');
  await form.waitFor();
  assert.ok(await pane.locator('[data-tool-panel-id="pmi"]').isVisible(), 'the PMI section is open on it');
  const value = form.getByRole('textbox', { name: 'Tolerance' });
  await value.click(); await value.fill('0.05'); await value.press('Enter');
  await pane.locator('[data-pmi-add]').click();
  await pane.getByRole('button', { name: 'Add flatness', exact: true }).waitFor();
  // Its tile stays while the new one waits in Quick Edit for the agent.
  assert.equal(await pane.getByRole('button', { name: 'PMI', exact: true }).count(), 1);
  assert.deepEqual(errors, []);
});

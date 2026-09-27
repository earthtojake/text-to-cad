import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { PNG } from 'pngjs';
import { serveStepHarness } from '../harness/stepScenario.mjs';

// Hover is drawn by the viewport's layers and by nothing else, so a hover re-renders those
// layers and nothing else: not the STEP surface, not its tool stack, not the Features tree.
// On a large assembly each of those renders cost about a second a hover. These tests count
// renders through React's devtools hook, and read the drawn frame to pin that what a hover
// lights is what it always lit.

let harness;
const cleanups = [];
before(async () => { harness = await serveStepHarness({ after: cleanup => cleanups.push(cleanup) }); });
after(async () => { for (const cleanup of cleanups.reverse()) await cleanup(); });

/**
 * Installed before the app: counts, per component name, the commits in which that component
 * rendered — its props or its hook state are not what they were at the last commit.
 */
function renderCounter() {
  const watched = new Set(['StepSurfaceBody', 'StepSceneLayers', 'ToolStack', 'ModelingTree', 'RendererShell']);
  const counts = Object.fromEntries([...watched].map(name => [name, 0]));
  const seen = new WeakMap();
  window.__renderCounts = counts;
  const nameOf = type => typeof type === 'function' ? (type.displayName || type.name)
    : type && typeof type === 'object' ? (type.displayName || type.type?.displayName || type.type?.name || type.render?.name || '') : '';
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, renderers: new Map(), inject() { return 1; }, checkDCE() {}, onScheduleFiberRoot() {},
    onCommitFiberUnmount() {}, onPostCommitFiberRoot() {}, setStrictMode() {},
    onCommitFiberRoot(_id, root) {
      const stack = [root.current];
      while (stack.length) {
        const fiber = stack.pop();
        const name = nameOf(fiber.type);
        if (watched.has(name)) {
          const last = seen.get(fiber) || (fiber.alternate && seen.get(fiber.alternate));
          if (!last || last.props !== fiber.memoizedProps || last.state !== fiber.memoizedState) {
            counts[name] += 1;
            const record = { props: fiber.memoizedProps, state: fiber.memoizedState };
            seen.set(fiber, record);
            if (fiber.alternate) seen.set(fiber.alternate, record);
          }
        }
        if (fiber.child) stack.push(fiber.child);
        if (fiber.sibling) stack.push(fiber.sibling);
      }
    },
  };
}

const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const MODEL = { y0: 55, y1: 570 };
function differing(left, right, { x0 = 0, y0 = MODEL.y0, x1 = left.width, y1 = MODEL.y1 } = {}) {
  let count = 0;
  for (let y = y0; y < y1; y += 1) for (let x = x0; x < x1; x += 1) {
    const offset = (y * left.width + x) * 4;
    if ([0, 1, 2].some(channel => Math.abs(left.data[offset + channel] - right.data[offset + channel]) > 2)) count += 1;
  }
  return count;
}
function projector(camera, box) {
  const sub = (a, b) => a.map((value, index) => value - b[index]);
  const norm = vector => { const length = Math.hypot(...vector); return vector.map(value => value / length); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a.reduce((sum, value, index) => sum + value * b[index], 0);
  const forward = norm(sub(camera.target, camera.position));
  const right = norm(cross(forward, camera.up));
  const up = cross(right, forward);
  const halfWidth = camera.halfHeight * (box.width / box.height);
  return point => {
    const offset = sub(point, camera.target);
    return [box.x + (dot(offset, right) / halfWidth * 0.5 + 0.5) * box.width,
      box.y + (0.5 - dot(offset, up) / camera.halfHeight * 0.5) * box.height];
  };
}

async function open() {
  const view = await harness.open({ init: renderCounter });
  const { page, pane } = view;
  // The harness serves no editing-preview feed, and each failed poll of it re-renders the
  // surface. Answer it as a server with nothing being edited does, so the surface is still.
  await page.route('**/__cad/preview?**', route => route.fulfill({ contentType: 'application/json', body: '{}' }));
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await pane.getByRole('region', { name: 'Features', exact: true }).waitFor();
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ axes: { enabled: false } }));
  await page.waitForTimeout(400);
  await settle(page);
  const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  // The tool strip and stack float over the canvas and change with every hover, so a frame is
  // shot without them -- except under a hovered Features row: hiding the row under the pointer
  // is itself a pointer leaving it, and the part it lit goes dark for the shot. Those frames
  // keep the stack and are read to its right.
  const frame = async ({ keepStack = false } = {}) => {
    await settle(page);
    return PNG.sync.read(await pane.locator('[aria-busy] > div > canvas').first().screenshot({ style: `[data-slot=popover-content], [data-slot=dropdown-menu-content], [data-slot=dropdown-menu-sub-content]${keepStack ? '' : ', [data-cad-tool-groups]'} { visibility: hidden !important; }` }));
  };
  /** The drawn frame once it satisfies `reached`; a repaint can land a frame or two late. */
  const frameWhen = async (reached, what, options) => {
    let last;
    for (let attempt = 0; attempt < 16; attempt += 1) {
      last = await frame(options);
      if (reached(last)) return last;
      await page.waitForTimeout(200);
    }
    assert.fail(`the drawn frame never ${what}`);
  };
  return {
    ...view, box, frame, frameWhen,
    at: projector(await page.evaluate(() => window.__cadCamera()), box),
    renders: () => page.evaluate(() => ({ ...window.__renderCounts })),
    /** Until the surface has been still for a second: a freshly opened file settles for a while. */
    quiet: async () => {
      let last = -1;
      for (let attempt = 0; attempt < 40; attempt += 1) {
        const count = await page.evaluate(() => window.__renderCounts.StepSurfaceBody);
        if (count === last) return;
        last = count;
        await page.waitForTimeout(1000);
      }
      assert.fail('the surface never stopped rendering');
    },
    selected: () => page.evaluate(() => window.cadHarness.a.controller.readState().selectedReferenceIds),
    away: () => page.mouse.move(box.x + 20, box.y + box.height - 20),
    chooseSelectMode: async name => {
      await page.evaluate(() => document.activeElement instanceof HTMLInputElement && document.activeElement.blur());
      await pane.getByRole('button', { name: /^Select mode: / }).click();
      await page.locator('[role=menu][aria-label="Select mode"]').getByRole('menuitemradio', { name, exact: true }).click();
      await page.locator('[role=menu]').waitFor({ state: 'detached' });
    },
  };
}

/** How many times each component rendered while `action` ran and its result settled. */
async function rendersDuring(view, action) {
  const before = await view.renders();
  await action();
  await view.page.waitForTimeout(300);
  await settle(view.page);
  const after = await view.renders();
  return Object.fromEntries(Object.keys(after).map(name => [name, after[name] - before[name]]));
}

test('a part hover, in the viewport or on a Features row, re-renders the viewport\'s layers and nothing above them', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  const still = await view.frame();
  await view.quiet();
  const overPart = await rendersDuring(view, async () => {
    await page.mouse.move(...at([6, 6, 5]));
    await view.frameWhen(shot => differing(still, shot) > 2000, 'lit the hovered part');
  });
  assert.ok(overPart.StepSceneLayers >= 1, `the layers drew the hover: ${JSON.stringify(overPart)}`);
  assert.deepEqual([overPart.StepSurfaceBody, overPart.ToolStack, overPart.ModelingTree, overPart.RendererShell], [0, 0, 0, 0],
    `nothing above the layers rendered for a hover: ${JSON.stringify(overPart)}`);
  const leaving = await rendersDuring(view, async () => {
    await view.away();
    await view.frameWhen(shot => differing(still, shot) === 0, 'let go of the part');
  });
  assert.deepEqual([leaving.StepSurfaceBody, leaving.ToolStack, leaving.ModelingTree], [0, 0, 0], JSON.stringify(leaving));

  // A Features row lights its part, and is a hover of the same kind.
  const row = pane.getByRole('button', { name: 'Select arm', exact: true });
  const stack = await pane.locator('[data-cad-tool-stack]').boundingBox();
  const beside = { x0: Math.ceil(stack.x + stack.width - view.box.x) + 4 };
  const stillBeside = await view.frame({ keepStack: true });
  const overRow = await rendersDuring(view, async () => {
    await row.hover();
    await view.frameWhen(shot => differing(stillBeside, shot, beside) > 2000, 'lit the part under the hovered row', { keepStack: true });
  });
  assert.ok(overRow.StepSceneLayers >= 1, JSON.stringify(overRow));
  assert.deepEqual([overRow.StepSurfaceBody, overRow.ToolStack, overRow.RendererShell], [0, 0, 0],
    `a row hover renders nothing above the layers: ${JSON.stringify(overRow)}`);
  await view.away();
  await view.frameWhen(shot => differing(still, shot) === 0, 'let go of the row\'s part');
  assert.deepEqual(errors, []);
});

test('under Faces, a hover over a selection draws what the selection draws: the hover lights over the selection and leaves it exactly as it was', async () => {
  const view = await open();
  const { page, at, errors } = view;
  // With a filter that matches nothing no Features row is on screen, so each part's faces load
  // on the press that picks one.
  await view.pane.getByRole('textbox', { name: 'Filter model', exact: true }).fill('zzz');
  await view.chooseSelectMode('Faces');
  // Two faces, one on each part; each press loads its part's faces and picks the face.
  await page.mouse.click(...at([15, 0, 4]));
  await page.waitForFunction(() => /\|o1\.2\.f\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  const armFace = (await view.selected())[0];
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => /\|o1\.1\.f\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  const baseFace = (await view.selected())[0];
  await view.away();
  await page.waitForTimeout(400);
  const selection = await view.frame();
  await view.quiet();

  // Hovering the other face lights it over the selection, and only the layers render for it.
  let hovered;
  const hover = await rendersDuring(view, async () => {
    await page.mouse.move(...at([15, 0, 4]));
    hovered = await view.frameWhen(shot => differing(selection, shot) > 200, 'lit the hovered face');
  });
  assert.deepEqual([hover.StepSurfaceBody, hover.ToolStack, hover.ModelingTree, hover.RendererShell], [0, 0, 0, 0],
    `a face hover renders nothing above the layers: ${JSON.stringify(hover)}`);
  assert.ok(hover.StepSceneLayers >= 1, JSON.stringify(hover));
  // Leaving restores the selection's frame exactly: the selection's own highlight was never touched.
  await view.away();
  await view.frameWhen(shot => differing(selection, shot) === 0, 'returned exactly to the selection once the pointer left');

  // Outside Measure a hover is drawn in the selection's style, so the hovered face over the
  // selection is the picture of both faces selected.
  await page.keyboard.down('Shift');
  await page.mouse.click(...at([15, 0, 4]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 2);
  assert.deepEqual(new Set(await view.selected()), new Set([armFace, baseFace]));
  await view.away();
  const both = await view.frameWhen(shot => differing(hovered, shot) === 0, 'drew the two selected faces as it drew one selected and one hovered');

  // A selected face under the pointer is drawn once, in the hover's style: the same picture.
  await page.mouse.move(...at([6, 6, 5]));
  await page.waitForTimeout(400);
  assert.equal(differing(both, await view.frame()), 0, 'a hovered selected face draws exactly as it does selected');
  await view.away();
  await page.waitForTimeout(400);
  assert.equal(differing(both, await view.frame()), 0, 'and leaving it changes nothing');
  assert.deepEqual(errors, []);
});

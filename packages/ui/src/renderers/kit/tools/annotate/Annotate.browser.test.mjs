import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runAnnotateScenario } from '../../../harness/annotateScenario.mjs';
import { serveXbfHarness } from '../../../harness/xbfScenario.mjs';

// The drawing tools under the frame that ships them: the engine document's renderer
// (`renderers/xbf`, which draws an .xbf and a STEP), over core's bracket fixture. They are kit
// tools, so the scenario itself (`harness/annotateScenario.mjs`) knows nothing about the frame. The
// controls row's tools and order are `RendererSurfaces.test.tsx`'s.

test('the drawing tools put ink into a transmissive model that orbits with it, undo, redo, recolour and clear, and stay when they are left — where Select picks, haloes and deletes it — and goes when the model updates', async (t) => {
  // Glass makes Three draw opaque objects for transmission and again for the main
  // view. Ink must survive those extra callbacks and leave orbit usable.
  const harness = await serveXbfHarness(t, { transmission: true });
  await runAnnotateScenario(await harness.open());
});

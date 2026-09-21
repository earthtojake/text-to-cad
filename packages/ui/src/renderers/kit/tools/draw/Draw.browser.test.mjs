import { test } from 'node:test';
import { runDrawScenario } from '../../../harness/drawScenario.mjs';
import { serveStepHarness } from '../../../harness/stepScenario.mjs';

// Draw under the frame that ships it: the STEP renderer, over the committed
// two-part fixture. It is a kit tool, so the scenario itself
// (`harness/drawScenario.mjs`) knows nothing about STEP.

test('Draw locks the view, pans model and ink together, keeps tools, colors and fills, and discards the sketch when left', async (t) => {
  const harness = await serveStepHarness(t);
  await runDrawScenario(await harness.open());
});

import assert from "node:assert/strict";
import test from "node:test";

import { animationClipOptions } from "./animationClipOptions.js";

test("the picker lists the model's authored clips and nothing else", () => {
  // The built-in "No clip" entry is gone: the transport's idle state is the
  // Animation section's gate switch, not a row in a list of clips. With one
  // kind of thing in the list there is nothing to separate it from, so the
  // "Clips" group heading went with it.
  assert.deepEqual(
    animationClipOptions([
      { id: "spin", label: "Spin" },
      { id: "walk", label: "Walk" }
    ]),
    [
      { value: "spin", label: "Spin" },
      { value: "walk", label: "Walk" }
    ]
  );
});

test("an authored clip called Rest is just a clip", () => {
  // The collision this list used to guard against — a built-in state entry
  // reading like an authored clip, beside a pose preset literally named `rest`
  // — is now structurally impossible: no entry here is a state.
  const options = animationClipOptions([{ id: "rest", label: "Rest" }]);
  assert.deepEqual(options, [{ value: "rest", label: "Rest" }]);
});

test("no clips yields no options", () => {
  // The section does not render without clips, so an empty list is empty — it
  // never falls back to an entry that stands for a state.
  assert.deepEqual(animationClipOptions(undefined), []);
  assert.deepEqual(animationClipOptions([]), []);
});

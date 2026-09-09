import assert from "node:assert/strict";
import test from "node:test";

import {
  markTutorialTipSeen,
  readSeenTutorialTipIds,
  resetTutorialTips,
  TUTORIAL_TIP_IDS,
  TUTORIAL_TIP_STORAGE_KEY,
  TUTORIAL_TIP_STORAGE_VERSION,
  tutorialTipSeen
} from "./persistence.js";

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, String(value));
    },
    removeItem: (key) => {
      values.delete(key);
    }
  };
}

test("a tip is unseen until it is marked, then stays seen", () => {
  const storage = createMemoryStorage();
  assert.equal(tutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage }), false);

  markTutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage });
  assert.equal(tutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage }), true);
  assert.deepEqual(readSeenTutorialTipIds({ storage }), [TUTORIAL_TIP_IDS.COPY_REFERENCE]);
});

test("marking the same tip twice does not duplicate it", () => {
  const storage = createMemoryStorage();
  markTutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage });
  markTutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage });
  assert.deepEqual(readSeenTutorialTipIds({ storage }), [TUTORIAL_TIP_IDS.COPY_REFERENCE]);
});

test("tips are tracked independently", () => {
  const storage = createMemoryStorage();
  markTutorialTipSeen("otherTip", { storage });
  assert.equal(tutorialTipSeen("otherTip", { storage }), true);
  assert.equal(tutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage }), false);
});

test("reset clears every seen tip", () => {
  const storage = createMemoryStorage();
  markTutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage });
  markTutorialTipSeen("otherTip", { storage });

  resetTutorialTips({ storage });
  assert.deepEqual(readSeenTutorialTipIds({ storage }), []);
  assert.equal(tutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage }), false);
});

test("a stored payload from another schema version re-arms the tips", () => {
  const storage = createMemoryStorage();
  storage.setItem(TUTORIAL_TIP_STORAGE_KEY, JSON.stringify({
    version: TUTORIAL_TIP_STORAGE_VERSION + 1,
    seen: [TUTORIAL_TIP_IDS.COPY_REFERENCE]
  }));
  assert.deepEqual(readSeenTutorialTipIds({ storage }), []);
});

test("unreadable storage reads as unseen rather than throwing", () => {
  const storage = {
    getItem: () => "{not json",
    setItem: () => {},
    removeItem: () => {}
  };
  assert.deepEqual(readSeenTutorialTipIds({ storage }), []);
  assert.equal(tutorialTipSeen(TUTORIAL_TIP_IDS.COPY_REFERENCE, { storage }), false);
});

test("an empty tip id is never seen and is never recorded", () => {
  const storage = createMemoryStorage();
  assert.equal(markTutorialTipSeen("", { storage }), false);
  assert.equal(tutorialTipSeen("", { storage }), false);
  assert.deepEqual(readSeenTutorialTipIds({ storage }), []);
});

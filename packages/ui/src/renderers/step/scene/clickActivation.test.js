import assert from "node:assert/strict";
import test from "node:test";
import { VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS, createClickActivation } from "./clickActivation.js";

/**
 * A gesture over a fake deferral: `run()` fires what was deferred, as the task queue would;
 * `deferred` keeps each entry's delay.
 */
function gesture({ doubleClick = true } = {}) {
  const commits = [];
  const deferred = [];
  const activation = createClickActivation({
    commit: (referenceId, options) => commits.push([referenceId, options]),
    doubleClick,
    defer: (fn, ms) => { deferred.push({ fn, ms }); return deferred.length; },
    cancel: (id) => { deferred[id - 1] = null; }
  });
  const run = () => { for (const entry of deferred.splice(0)) entry?.fn(); };
  return { activation, commits, deferred, run };
}

test("a first click commits at once, nothing deferred", () => {
  const { activation, commits, deferred } = gesture();
  activation.tap(1, "o1.1", { multiSelect: false });
  assert.deepEqual(commits, [["o1.1", { multiSelect: false }]]);
  assert.deepEqual(deferred, []);
});

test("a click with no count (a pointer that reports none) commits at once too", () => {
  const { activation, commits, deferred } = gesture();
  activation.tap(0, "o1.1", {});
  assert.equal(commits.length, 1);
  assert.deepEqual(deferred, []);
});

test("the second click of a double-click commits nothing of its own: the dblclick owns the gesture and says the first click activated", () => {
  const { activation, commits, deferred, run } = gesture();
  activation.tap(1, "o1.1", { multiSelect: false });
  activation.tap(2, "o1.1", { multiSelect: false });
  assert.equal(commits.length, 1, "the second click is held");
  assert.equal(deferred.filter(Boolean).length, 1);
  assert.equal(activation.double(), true, "the first click's activation is on record for the double-click to undo");
  run();
  assert.equal(commits.length, 1, "the dblclick cancelled the second click's activation");
});

test("a second click the browser does not follow with dblclick commits after the event, as a click of its own", () => {
  const { activation, commits, run } = gesture();
  activation.tap(1, "o1.1", {});
  activation.tap(2, "o1.2", { multiSelect: true });
  run();
  assert.deepEqual(commits.map(([id]) => id), ["o1.1", "o1.2"]);
  assert.equal(activation.double(), true, "and counts as the first click of whatever double-click follows");
});

test("a first press that was not a tap (a drag, a cancel) leaves no click for the double-click to undo", () => {
  const { activation, commits } = gesture();
  activation.tap(1, "o1.1", {});
  activation.miss(1);
  activation.tap(2, "o1.1", {});
  assert.equal(commits.length, 1);
  assert.equal(activation.double(), false, "the earlier click belongs to an earlier gesture");
});

test("a second press that was not a tap keeps the first click on record", () => {
  const { activation } = gesture();
  activation.tap(1, "o1.1", {});
  activation.miss(2);
  assert.equal(activation.double(), true);
});

test("the double-click consumes the record: a third click starts over", () => {
  const { activation, commits, run } = gesture();
  activation.tap(1, "o1.1", {});
  activation.tap(2, "o1.1", {});
  assert.equal(activation.double(), true);
  assert.equal(activation.double(), false, "nothing to undo twice");
  activation.tap(3, "o1.1", {});
  assert.equal(commits.length, 1, "a third click is held like a second: the browser may pair it");
  run();
  assert.equal(commits.length, 2);
  assert.equal(activation.double(), true);
});

test("cancel drops a held second click and nothing else", () => {
  const { activation, commits, run } = gesture();
  activation.tap(1, "o1.1", {});
  activation.tap(2, "o1.1", {});
  activation.cancel();
  run();
  assert.equal(commits.length, 1);
  assert.equal(activation.double(), true, "the first click still activated");
});

test("without double-click (a coarse pointer) every tap commits at once", () => {
  const { activation, commits, deferred } = gesture({ doubleClick: false });
  activation.tap(1, "o1.1", {});
  activation.tap(2, "o1.1", {});
  activation.tap(3, "o1.1", {});
  assert.equal(commits.length, 3);
  assert.deepEqual(deferred, []);
});

test("a tap under a tool a pick would leave waits the double-click window, as every click once did", () => {
  const { activation, commits, deferred, run } = gesture();
  activation.tap(1, "o1.1", { multiSelect: false }, { wait: true });
  assert.deepEqual(commits, [], "nothing until the window has passed");
  assert.deepEqual(deferred.map((entry) => entry?.ms), [VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS]);
  run();
  assert.deepEqual(commits, [["o1.1", { multiSelect: false }]], "a lone click commits after it");
  assert.equal(activation.double(), true);
});

test("a double-click under such a tool cancels the waiting click: nothing activated, nothing to undo", () => {
  const { activation, commits, run } = gesture();
  activation.tap(1, "o1.1", {}, { wait: true });
  activation.tap(2, "o1.1", {}, { wait: true });
  assert.equal(activation.double(), false, "no click of this gesture activated");
  run();
  assert.deepEqual(commits, [], "neither click commits: the tool never changed hands");
});

test("a right tap or a second finger drops a waiting click", () => {
  const { activation, commits, run } = gesture();
  activation.tap(1, "o1.1", {}, { wait: true });
  activation.cancel();
  run();
  assert.deepEqual(commits, []);
  assert.equal(activation.double(), false);
});

test("without double-click (a coarse pointer) a tap that would wait commits at once", () => {
  const { activation, commits, deferred } = gesture({ doubleClick: false });
  activation.tap(1, "o1.1", {}, { wait: true });
  assert.equal(commits.length, 1);
  assert.deepEqual(deferred, []);
});

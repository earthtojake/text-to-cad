import assert from "node:assert/strict";
import test from "node:test";

import { renderHook } from "../../../../scripts/reactHarness.mjs";
import { useViewerAutoReload } from "./useViewerAutoReload.js";

// A hand-driven clock and timer queue: the hook's whole job is a poll loop, and
// a test of a poll loop that sleeps is a flaky test.
function driver(answers) {
  const queued = [];
  const reloads = [];
  let clock = 0;
  const remaining = [...answers];
  return {
    reloads,
    get clock() {
      return clock;
    },
    options: {
      fetchServerInfo: async () => remaining.shift() ?? { ok: true, identityToken: "a" },
      reload: () => reloads.push(clock),
      now: () => clock,
      schedule: (run, delayMs) => {
        queued.push({ run, delayMs });
        return queued.length;
      },
      cancel: () => {}
    },
    async advance() {
      const next = queued.shift();
      if (!next) {
        return false;
      }
      clock += next.delayMs;
      await next.run();
      return true;
    },
    get scheduled() {
      return queued.length;
    }
  };
}

async function drain(harness, drive, steps) {
  for (let index = 0; index < steps; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    if (!(await drive.advance())) {
      break;
    }
    harness.update();
  }
}

test("a production viewer never polls and never reloads", async () => {
  const drive = driver([]);
  const harness = renderHook(
    (props) => useViewerAutoReload(props.serverInfo, drive.options),
    { serverInfo: { autoReload: false, identityToken: "a" } }
  );
  assert.equal(harness.result, false);
  assert.equal(drive.scheduled, 0, "no poll is scheduled at all");
  harness.unmount();
});

test("a restarted development backend reloads the page once it answers again", async () => {
  const drive = driver([
    { ok: true, identityToken: "a" },
    { ok: false },
    { ok: false },
    { ok: true, identityToken: "b" }
  ]);
  const harness = renderHook(
    (props) => useViewerAutoReload(props.serverInfo, drive.options),
    { serverInfo: { autoReload: true, identityToken: "a" } }
  );

  await drain(harness, drive, 1);
  assert.equal(harness.result, false, "the unchanged server shows nothing");

  await drain(harness, drive, 1);
  assert.equal(harness.result, true, "the closed port shows the reloading status");
  assert.deepEqual(drive.reloads, []);

  await drain(harness, drive, 2);
  assert.equal(drive.reloads.length, 1, "the page reloads exactly once");
  assert.equal(drive.scheduled, 0, "and stops polling after it");
  harness.unmount();
});

test("an unchanged server that blips does not reload the page", async () => {
  const drive = driver([
    { ok: false },
    { ok: true, identityToken: "a" },
    { ok: true, identityToken: "a" }
  ]);
  const harness = renderHook(
    (props) => useViewerAutoReload(props.serverInfo, drive.options),
    { serverInfo: { autoReload: true, identityToken: "a" } }
  );
  await drain(harness, drive, 3);
  assert.deepEqual(drive.reloads, []);
  assert.equal(harness.result, false, "the reloading status is withdrawn");
  harness.unmount();
});

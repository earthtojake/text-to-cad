// Who owns the theme panel and the file sheet, and what a toggle does to the
// pair. The standalone viewer passes neither prop, so "not controlled" must
// keep meaning "the surface's own flag" — a default that flipped here would
// change the shipping app's behaviour with no test in front of it.
import assert from "node:assert/strict";
import test from "node:test";

import {
  HOST_PANEL,
  isHostPanelControlled,
  nextPanelState,
  resolveHostPanelOpen
} from "./hostPanels.js";

test("only a boolean claims a panel", () => {
  assert.equal(isHostPanelControlled(true), true);
  assert.equal(isHostPanelControlled(false), true);
  assert.equal(isHostPanelControlled(undefined), false);
  assert.equal(isHostPanelControlled(null), false);
  // Not truthiness: a host that means "closed" says `false`, and a host that
  // means nothing says nothing.
  assert.equal(isHostPanelControlled(0), false);
  assert.equal(isHostPanelControlled(""), false);
  assert.equal(isHostPanelControlled("true"), false);
});

test("observing is uncontrolled: a callback alone does not take the flag", () => {
  // The desktop app starts here so the surface's own default — a STEP file
  // opens with its sheet up — is what it hears, instead of a second copy of
  // the rule that produces it. A callback is not a claim.
  assert.equal(isHostPanelControlled(null), false);
  assert.equal(resolveHostPanelOpen(null, true), true);
  // And echoing the report back is what makes it controlled.
  assert.equal(isHostPanelControlled(true), true);
  assert.equal(resolveHostPanelOpen(true, false), true);
});

test("uncontrolled reads the surface's own flag; controlled reads the host's", () => {
  assert.equal(resolveHostPanelOpen(undefined, true), true);
  assert.equal(resolveHostPanelOpen(undefined, false), false);
  assert.equal(resolveHostPanelOpen(null, true), true);
  // A host's `false` beats an own flag left open, and its `true` beats a
  // closed one — that is what controlled means.
  assert.equal(resolveHostPanelOpen(false, true), false);
  assert.equal(resolveHostPanelOpen(true, false), true);
  // Nothing on either side is closed.
  assert.equal(resolveHostPanelOpen(undefined, undefined), false);
});

test("a toggle flips its own panel when nothing else is up", () => {
  assert.deepEqual(
    nextPanelState({ themeEditing: false, fileSheetOpen: false }, HOST_PANEL.THEME),
    { themeEditing: true, fileSheetOpen: false }
  );
  assert.deepEqual(
    nextPanelState({ themeEditing: true, fileSheetOpen: false }, HOST_PANEL.THEME),
    { themeEditing: false, fileSheetOpen: false }
  );
  assert.deepEqual(
    nextPanelState({ themeEditing: false, fileSheetOpen: false }, HOST_PANEL.FILE_SHEET),
    { themeEditing: false, fileSheetOpen: true }
  );
  assert.deepEqual(
    nextPanelState({ themeEditing: false, fileSheetOpen: true }, HOST_PANEL.FILE_SHEET),
    { themeEditing: false, fileSheetOpen: false }
  );
});

test("opening one closes the other, and a toggle over the other one opens", () => {
  // The theme panel up, the sheet's toggle pressed: the sheet takes the panel
  // rather than the press closing an already-closed sheet and doing nothing.
  assert.deepEqual(
    nextPanelState({ themeEditing: true, fileSheetOpen: false }, HOST_PANEL.FILE_SHEET),
    { themeEditing: false, fileSheetOpen: true }
  );
  assert.deepEqual(
    nextPanelState({ themeEditing: false, fileSheetOpen: true }, HOST_PANEL.THEME),
    { themeEditing: true, fileSheetOpen: false }
  );
  // And an explicit open says the same thing.
  assert.deepEqual(
    nextPanelState({ themeEditing: true, fileSheetOpen: false }, HOST_PANEL.FILE_SHEET, true),
    { themeEditing: false, fileSheetOpen: true }
  );
});

test("an explicit close closes only what it names", () => {
  assert.deepEqual(
    nextPanelState({ themeEditing: true, fileSheetOpen: false }, HOST_PANEL.THEME, false),
    { themeEditing: false, fileSheetOpen: false }
  );
  assert.deepEqual(
    nextPanelState({ themeEditing: false, fileSheetOpen: true }, HOST_PANEL.THEME, false),
    { themeEditing: false, fileSheetOpen: true }
  );
  assert.deepEqual(
    nextPanelState({ themeEditing: true, fileSheetOpen: false }, HOST_PANEL.FILE_SHEET, false),
    { themeEditing: true, fileSheetOpen: false }
  );
});

test("both closed is a reachable state, and nothing is ever both", () => {
  for (const start of [
    { themeEditing: false, fileSheetOpen: false },
    { themeEditing: true, fileSheetOpen: false },
    { themeEditing: false, fileSheetOpen: true }
  ]) {
    for (const panel of [HOST_PANEL.THEME, HOST_PANEL.FILE_SHEET]) {
      for (const open of [undefined, true, false]) {
        const next = nextPanelState(start, panel, open);
        assert.ok(
          !(next.themeEditing && next.fileSheetOpen),
          `both open from ${JSON.stringify(start)} ${panel} ${String(open)}`
        );
      }
    }
  }
  assert.deepEqual(nextPanelState(undefined, HOST_PANEL.THEME, false), {
    themeEditing: false,
    fileSheetOpen: false
  });
});

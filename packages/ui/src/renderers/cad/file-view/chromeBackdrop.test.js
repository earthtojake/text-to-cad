// The "System" theme's backdrop: the chrome's own ground, in the three
// contexts the surface renders in.
//
// The load-bearing case is the LAST one. A headless snapshot has no document
// and no stylesheet, so the fallback pair is the whole answer there — and it
// has to be the same colour the tokens resolve to, or the same theme would
// paint one background on screen and another in a rendered picture.
import assert from "node:assert/strict";
import test from "node:test";

import {
  CHROME_BACKDROP_FALLBACK,
  cssColorToHex,
  readChromeBackgroundToken,
  resolveChromeBackdropColor,
  sceneBackdropEdgeColor
} from "./chromeBackdrop.js";

test("the shadcn pair resolves to the written-out fallback, exactly", () => {
  // If these two ever disagree, a snapshot and the screen disagree.
  assert.equal(cssColorToHex("oklch(1 0 0)"), CHROME_BACKDROP_FALLBACK.light);
  assert.equal(cssColorToHex("oklch(0.145 0 0)"), CHROME_BACKDROP_FALLBACK.dark);
});

test("oklch: percentages, hue units, chroma and `none`", () => {
  assert.equal(cssColorToHex("oklch(100% 0 0)"), "#ffffff");
  assert.equal(cssColorToHex("oklch(0 0 0)"), "#000000");
  assert.equal(cssColorToHex("oklch(1 0 0 / 50%)"), "#ffffff");
  assert.equal(cssColorToHex("oklch(none none none)"), "#000000");
  // A real chroma, and the same colour written with each hue unit.
  const red = cssColorToHex("oklch(0.628 0.2577 29.23)");
  assert.match(red, /^#[0-9a-f]{6}$/u);
  assert.equal(cssColorToHex("oklch(0.628 0.2577 29.23deg)"), red);
  assert.equal(cssColorToHex("oklch(0.628 0.2577 0.08119turn)"), red);
  // Roughly sRGB red, which is what that triple is.
  assert.equal(red.slice(1, 3), "ff");
});

test("hex and rgb() come through; anything else is nothing", () => {
  assert.equal(cssColorToHex("#FFFFFF"), "#ffffff");
  assert.equal(cssColorToHex("#abc"), "#aabbcc");
  assert.equal(cssColorToHex("rgb(255, 255, 255)"), "#ffffff");
  assert.equal(cssColorToHex("rgb(10 10 10 / 0.5)"), "#0a0a0a");
  assert.equal(cssColorToHex("rgba(0, 0, 0, 1)"), "#000000");
  assert.equal(cssColorToHex("color-mix(in srgb, red 50%, blue)"), null);
  assert.equal(cssColorToHex("white"), null);
  assert.equal(cssColorToHex(""), null);
  assert.equal(cssColorToHex(null), null);
  assert.equal(cssColorToHex("oklch(1 0)"), null);
  assert.equal(cssColorToHex("oklch(1 0 nope)"), null);
});

test("with a document, the token is the backdrop", () => {
  // The desktop app and the standalone viewer: `--background` is on <html>,
  // and the `.dark` class swaps the pair under it.
  const doc = (token) => ({
    documentElement: {},
    defaultView: { getComputedStyle: () => ({ getPropertyValue: () => token }) }
  });
  assert.equal(readChromeBackgroundToken(doc(" oklch(1 0 0) ")), "oklch(1 0 0)");
  assert.equal(
    resolveChromeBackdropColor({ token: readChromeBackgroundToken(doc("oklch(0.145 0 0)")), prefersDark: true }),
    "#0a0a0a"
  );
  // The token wins over the app's light/dark: a host that themes its chrome
  // some other colour gets that colour, not the default pair.
  assert.equal(
    resolveChromeBackdropColor({ token: "#123456", prefersDark: true }),
    "#123456"
  );
});

test("with no document — a headless snapshot — the fallback pair is the answer", () => {
  assert.equal(readChromeBackgroundToken(null), "");
  assert.equal(readChromeBackgroundToken({}), "");
  assert.equal(readChromeBackgroundToken({ documentElement: {} }), "");
  assert.equal(resolveChromeBackdropColor({ token: "", prefersDark: false }), "#ffffff");
  assert.equal(resolveChromeBackdropColor({ token: "", prefersDark: true }), "#0a0a0a");
  assert.equal(resolveChromeBackdropColor(), "#ffffff");
  // An unreadable token is a missing one, not a crash.
  assert.equal(
    resolveChromeBackdropColor({ token: "color-mix(in srgb, var(--x) 38%, transparent)", prefersDark: true }),
    "#0a0a0a"
  );
});

test("the box behind the canvas takes the scene's edge colour", () => {
  assert.equal(sceneBackdropEdgeColor({ type: "solid", solidColor: "#101010" }), "#101010");
  // A gradient ends on its outer stop, and that is the edge of the picture.
  assert.equal(
    sceneBackdropEdgeColor({ type: "linear", solidColor: "#edf5fb", linearStart: "#fbfdff", linearEnd: "#b8cadb" }),
    "#b8cadb"
  );
  assert.equal(
    sceneBackdropEdgeColor({ type: "radial", solidColor: "#111111", radialInner: "#23242a", radialOuter: "#0a0a0d" }),
    "#0a0a0d"
  );
  // A type with no stop of its own falls back through the solid base to the
  // caller's colour, which is the System theme's chrome background.
  assert.equal(sceneBackdropEdgeColor({ type: "linear", solidColor: "#222222" }), "#222222");
  assert.equal(sceneBackdropEdgeColor(null, "#0a0a0a"), "#0a0a0a");
  assert.equal(sceneBackdropEdgeColor({}, "#0a0a0a"), "#0a0a0a");
  assert.equal(sceneBackdropEdgeColor(null), "#ffffff");
});

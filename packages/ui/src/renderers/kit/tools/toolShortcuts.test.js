import assert from "node:assert/strict";
import test from "node:test";
import { ZOOM_FACTOR, ariaShortcut, pressToolKey, pressZoomKey, shortcutOfEvent, zoomShortcuts } from "./toolShortcuts.js";

const key = (code, extra = {}) => ({ code, key: code.slice(3).toLowerCase(), ...extra });

test("a key is its letter, Shift its ⇧, and nothing with ⌘, Ctrl or Alt held", () => {
  assert.equal(shortcutOfEvent(key("KeyV")), "V");
  assert.equal(shortcutOfEvent(key("KeyL", { shiftKey: true })), "⇧L");
  for (const held of ["metaKey", "ctrlKey", "altKey"]) assert.equal(shortcutOfEvent(key("KeyV", { [held]: true })), null);
  assert.equal(shortcutOfEvent({ code: "Digit1", key: "1" }), null);
  assert.equal(ariaShortcut("⇧L"), "Shift+L");
});

test("a key takes up its tool, a drawing tool's its strip tool with that tool in hand, and F frames the model", () => {
  const taken = [];
  const tool = (id, shortcut, extra = {}) => ({ id, shortcut, onSelect: () => taken.push(id), ...extra });
  const drawn = [];
  let fitted = 0;
  const tools = [tool("references", "V", { active: true }), tool("pencil"), tool("shapes"), tool("measure", "M"), tool("clip")];
  const options = { tools, selectDrawing: id => drawn.push(id), fit: () => { fitted += 1; } };
  assert.equal(pressToolKey(key("KeyM"), options), true);
  assert.equal(pressToolKey(key("KeyV"), options), true, "the tool in hand stays so");
  assert.equal(pressToolKey(key("KeyL", { shiftKey: true }), options), true);
  assert.equal(pressToolKey(key("KeyP"), options), true);
  assert.equal(pressToolKey(key("KeyF"), options), true);
  assert.deepEqual([taken, drawn, fitted], [["measure", "shapes", "pencil"], ["arrow", "freedraw"], 1]);
  assert.equal(pressToolKey(key("KeyQ"), options), false, "a key no tool has");
  assert.equal(pressToolKey(key("KeyM"), { ...options, tools: [tool("measure", "M", { disabled: true })] }), false);
});

test("the zoom's keys: + and - (⌘ or Ctrl too) zoom, ⇧1 fits, ⇧2 frames what is picked, ⇧0 is 100%", () => {
  const calls = [];
  const zoom = { zoomBy: f => calls.push(["by", f]), fit: () => calls.push(["fit"]), zoomTo100: () => calls.push(["100"]),
    zoomToSelection: () => calls.push(["selection"]), selectionAvailable: false };
  const press = (event, on = zoom) => pressZoomKey(event, on);
  assert.equal(press({ key: "=", code: "Equal" }), true);
  assert.equal(press({ key: "+", code: "Equal", shiftKey: true }), true);
  assert.equal(press({ key: "=", code: "Equal", metaKey: true }), true);
  assert.equal(press({ key: "-", code: "Minus" }), true);
  assert.equal(press({ key: "-", code: "Minus", ctrlKey: true }), true);
  assert.equal(press({ key: "!", code: "Digit1", shiftKey: true }), true);
  assert.equal(press({ key: ")", code: "Digit0", shiftKey: true }), true);
  assert.equal(press({ key: "@", code: "Digit2", shiftKey: true }), false, "nothing picked: no selection to frame");
  assert.equal(press({ key: "@", code: "Digit2", shiftKey: true }, { ...zoom, selectionAvailable: true }), true);
  assert.deepEqual(calls, [["by", ZOOM_FACTOR], ["by", ZOOM_FACTOR], ["by", ZOOM_FACTOR], ["by", 1 / ZOOM_FACTOR], ["by", 1 / ZOOM_FACTOR],
    ["fit"], ["100"], ["selection"]]);
  // 100% is the fit where the view has no other.
  calls.length = 0;
  assert.equal(press({ key: ")", code: "Digit0", shiftKey: true }, { ...zoom, zoomTo100: null }), true);
  assert.deepEqual(calls, [["fit"]]);
  for (const event of [{ key: "1", code: "Digit1" }, { key: "=", code: "Equal", altKey: true }, { key: "!", code: "Digit1", shiftKey: true, metaKey: true }, { key: "f", code: "KeyF" }]) {
    assert.equal(press(event), false);
  }
  assert.equal(pressZoomKey({ key: "=" }, null), false, "a view that takes no zoom keys");
  assert.deepEqual([zoomShortcuts("darwin").in, zoomShortcuts("win32").out, zoomShortcuts("linux").actual], ["⌘+", "Ctrl+-", "⇧0"]);
});

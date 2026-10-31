import assert from "node:assert/strict";
import test from "node:test";
import { ariaShortcut, pressToolKey, shortcutOfEvent } from "./toolShortcuts.js";

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

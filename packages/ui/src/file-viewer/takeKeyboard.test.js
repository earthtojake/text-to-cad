import assert from "node:assert/strict";
import test from "node:test";
import { mayTakeKeyboard } from "./takeKeyboard.js";

test("a view opening takes the keyboard only where nothing has it, and never inside a frame", () => {
  const body = {}, field = {};
  const page = { body, documentElement: {}, activeElement: body };
  const top = {}; top.top = top;
  assert.equal(mayTakeKeyboard(page, top), true, "a page of its own, its body focused");
  assert.equal(mayTakeKeyboard({ ...page, activeElement: field }, top), false, "a field has it");
  assert.equal(mayTakeKeyboard(page, { top }), false, "a card in a chat's frame");
  const foreign = { get top() { throw new Error("cross-origin"); } };
  assert.equal(mayTakeKeyboard(page, foreign), false, "a frame another origin holds");
});

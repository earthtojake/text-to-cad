import assert from "node:assert/strict";
import test from "node:test";
import { clampNumber, decimalsOf, formatNumber, isLengthUnit, readTyped, splitValueText } from "./numberText.js";

test("a value's text is its number, the space before its unit, and its unit", () => {
  assert.deepEqual(splitValueText("7.3 mm"), { number: "7.3", space: " ", unit: "mm" });
  assert.deepEqual(splitValueText("45°"), { number: "45", space: "", unit: "°" });
  assert.deepEqual(splitValueText("-1.5 EV"), { number: "-1.5", space: " ", unit: "EV" });
  assert.deepEqual(splitValueText("5"), { number: "5", space: "", unit: "" });
});

test("what is typed is read in the field's unit: another length or angle converted, any other unit unknown", () => {
  assert.deepEqual(readTyped("8.25", "mm"), { kind: "number", value: 8.25 });
  assert.deepEqual(readTyped(" 8 MM ", "mm"), { kind: "number", value: 8 });
  assert.deepEqual(readTyped("1in", "mm"), { kind: "number", value: 25.4 });
  assert.deepEqual(readTyped("2 cm", "mm"), { kind: "number", value: 20 });
  assert.deepEqual(readTyped("1 ft", "in"), { kind: "number", value: 12 });
  assert.ok(Math.abs(readTyped("1 rad", "°").value - 57.29578) < 1e-4);
  assert.deepEqual(readTyped("5 kg", "mm"), { kind: "unit", unit: "kg" });
  assert.deepEqual(readTyped("5 mm", ""), { kind: "unit", unit: "mm" });
  assert.deepEqual(readTyped("5 mm", "%"), { kind: "unit", unit: "mm" });
  assert.deepEqual(readTyped("abc", "mm"), { kind: "invalid" });
  assert.deepEqual(readTyped("", "mm"), { kind: "invalid" });
  assert.equal(isLengthUnit("mm"), true);
  assert.equal(isLengthUnit("°"), false);
});

test("numbers are written at a precision, and kept in a range", () => {
  assert.deepEqual([decimalsOf("0.05"), decimalsOf("7"), decimalsOf(1e-7)], [2, 0, 7]);
  assert.deepEqual([formatNumber(9, 1), formatNumber(-0.04, 1), formatNumber(127.00001, 0)], ["9.0", "0.0", "127"]);
  assert.deepEqual([clampNumber(50, 3, 9), clampNumber(-5, 3, undefined), clampNumber(5, undefined, undefined)], [9, 3, 5]);
});

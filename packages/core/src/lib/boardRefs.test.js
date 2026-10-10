import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildBoardRefToken,
  formatBoardRefSelector,
  isBoardRefPath,
  parseBoardRefSelector,
  parseBoardRefToken,
  splitBoardRefSelectors,
} from "./boardRefs.js";

// The same fixture cadgen/kicad/refs.py asserts: one language, two implementations.
const fixture = JSON.parse(readFileSync(new URL("./boardRefs.parity.json", import.meta.url), "utf8"));

test("every selector case parses as the fixture says", () => {
  for (const { selector, kind, ref, pad, net, at, canonical } of fixture.selectorCases) {
    const parsed = parseBoardRefSelector(selector);
    assert.ok(parsed, selector);
    assert.equal(parsed.kind, kind, selector);
    assert.equal(parsed.canonical, canonical, selector);
    assert.equal(parsed.ref, ref, selector);
    assert.equal(parsed.pad, pad, selector);
    assert.equal(parsed.net, net, selector);
    assert.deepEqual(parsed.at, at, selector);
  }
});

test("what is not a board reference is refused", () => {
  for (const selector of fixture.invalidSelectors) {
    assert.equal(parseBoardRefSelector(selector), null, JSON.stringify(selector));
  }
});

test("formatting gives the canonical selector", () => {
  for (const { selector, ...fields } of fixture.formatCases) {
    assert.equal(formatBoardRefSelector(fields), selector);
    assert.equal(parseBoardRefSelector(selector).canonical, selector);
  }
});

test("tokens split their selectors outside quotes and rebuild the same", () => {
  for (const { token, path, selectors } of fixture.tokenCases) {
    assert.deepEqual(parseBoardRefToken(token), { path, selectors }, token);
    assert.equal(buildBoardRefToken({ path, selectors }), token);
  }
});

test("a token with whitespace outside a quoted name is no token", () => {
  for (const token of fixture.invalidTokens) assert.equal(parseBoardRefToken(token), null, token);
});

test("a host's list of selectors splits outside quotes", () => {
  assert.deepEqual(splitBoardRefSelectors('#U3, #net:"a,b" ,net:VIN@x1y2,'), ["#U3", '#net:"a,b"', "net:VIN@x1y2"]);
  assert.deepEqual(splitBoardRefSelectors(""), []);
});

test("only KiCad documents speak this language", () => {
  assert.ok(isBoardRefPath("PCB/board.kicad_pcb"));
  assert.ok(isBoardRefPath("x.KICAD_SCH"));
  assert.ok(!isBoardRefPath("part.step"));
  assert.throws(() => buildBoardRefToken({ path: "b.kicad_pcb", selectors: ["o1.f2.e3"] }), /not a board reference/);
});

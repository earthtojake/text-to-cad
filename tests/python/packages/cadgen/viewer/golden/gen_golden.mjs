// Parity-oracle generator. Run with Node from the app root:
//
//   node tests/python/packages/cadgen/viewer/golden/gen_golden.mjs
//
// Writes two files:
//   tests/python/packages/cadgen/viewer/golden/golden.json  fixture for the Python encoder tests
//   server/collation.json            RUNTIME collation table shipped in the bundle
//
// The oracle here is the JavaScript LANGUAGE, not our copy of it: every expected
// value comes from Node's own encodeURIComponent / URLSearchParams /
// BigInt.prototype.toString(36) / decodeURIComponent / Intl.Collator. Nothing is
// imported from server/, so the fixture cannot drift into agreement with a buggy
// implementation on either side.
//
// Performance note: `localeCompare(a, b, undefined, opts)` constructs a fresh
// Intl.Collator on EVERY call (measured 415ms vs 9ms for 200k comparisons — 46x).
// One cached collator is used throughout; it is sign-identical to localeCompare
// with the same options, and the fixture pins that equivalence.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(HERE, "..", "..");

const COLLATOR_OPTIONS = { numeric: true, sensitivity: "base" };
const collator = new Intl.Collator(undefined, COLLATOR_OPTIONS);
const cmp = collator.compare;

// ---------------------------------------------------------------------------
// 1. The collation model, derived from the collator
// ---------------------------------------------------------------------------

const MAX_CODEPOINT = 0x10ffff;
// Codepoints below this get an exhaustive expansion search. Above it, only the
// NFKD/toLowerCase guesses run — those cover fullwidth, ligature and
// presentation forms, which is everything up there that expands.
const EXHAUSTIVE_LIMIT = 0x2200;

function buildCollationModel() {
  // Python NFD-normalises before it looks anything up, so a codepoint that is
  // not NFD-stable can never reach the tables. Skipping them is what keeps the
  // fixture at half a megabyte instead of several.
  const codepoints = [];
  for (let cp = 0; cp <= MAX_CODEPOINT; cp += 1) {
    if (cp >= 0xd800 && cp <= 0xdfff) continue;
    const ch = String.fromCodePoint(cp);
    if (ch.normalize("NFD") !== ch) continue;
    codepoints.push(cp);
  }

  // (a) L1-ignorable: contributes no primary weight in context.
  const ignorable = new Set();
  for (const cp of codepoints) {
    if (cmp("m" + String.fromCodePoint(cp) + "m", "mm") === 0) ignorable.add(cp);
  }

  // (b) Expansions. Multi-character candidates are LETTERS only: with numeric
  // collation on, "0" and "00" compare equal, so a digit-bearing candidate list
  // is not an order and the binary search hands '0' back an expansion to "00".
  const ALPHA = "abcdefghijklmnopqrstuvwxyz";
  const candidates = "0123456789".split("");
  for (const a of ALPHA) candidates.push(a);
  for (const a of ALPHA) for (const b of ALPHA) candidates.push(a + b);
  for (const a of ALPHA) for (const b of ALPHA) for (const c of ALPHA) candidates.push(a + b + c);
  candidates.sort((a, b) => cmp("m" + a + "m", "m" + b + "m"));

  function exhaustive(ch) {
    const probe = "m" + ch + "m";
    let lo = 0;
    let hi = candidates.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const sign = cmp(probe, "m" + candidates[mid] + "m");
      if (sign === 0) return candidates[mid];
      if (sign < 0) hi = mid - 1;
      else lo = mid + 1;
    }
    return null;
  }

  const rawExpansion = new Map();
  for (const cp of codepoints) {
    if (ignorable.has(cp)) continue;
    const ch = String.fromCodePoint(cp);
    const probe = "m" + ch + "m";
    let found = null;
    // Guesses first (cheap and they cover most of the repertoire), each VERIFIED
    // against the collator — NFKD alone is wrong, e.g. U+00B2 decomposes to "2"
    // but does not collate equal to it.
    for (const guess of [ch.normalize("NFKD").toLowerCase(), ch.toLowerCase(), ch.normalize("NFKD")]) {
      if (!guess || guess === ch) continue;
      if (cmp(probe, "m" + guess + "m") === 0) {
        found = guess;
        break;
      }
    }
    if (found === null && cp < EXHAUSTIVE_LIMIT) found = exhaustive(ch);
    if (found !== null && found !== ch) rawExpansion.set(cp, found);
  }

  // An expansion's own characters can decompose or expand again (Arabic
  // presentation forms expand to sequences carrying combining marks), so drive
  // every value to a fixed point HERE. The Python side then does one lookup and
  // never guesses.
  function expandOnce(text) {
    let out = "";
    for (const ch of text.normalize("NFD")) {
      const exp = rawExpansion.get(ch.codePointAt(0));
      out += exp === undefined ? ch : exp;
    }
    return out;
  }
  const expansion = new Map();
  for (const [cp, value] of rawExpansion) {
    let current = value;
    for (let depth = 0; depth < 8; depth += 1) {
      const next = expandOnce(current);
      if (next === current) break;
      current = next;
    }
    expansion.set(cp, current);
  }

  const atoms = codepoints.filter((cp) => !ignorable.has(cp) && !expansion.has(cp));

  // (c) CONTRACTIONS. An L1-ignorable is ignorable ON ITS OWN, but after some
  // bases it forms a unit with its own primary weight — ICU contracts
  // ARABIC ALEF + HAMZA ABOVE into the weight of ALEF WITH HAMZA ABOVE, which
  // is NOT alef's. Measured: cmp("mٔm","mm") === 0 (ignorable) yet
  // cmp("mأm","mاm") === -1 (not ignorable there).
  //
  // Without this pass a per-character model misorders every Arabic hamza,
  // madda and wasla variant, and the whole class is invisible to a corpus that
  // does not contain them. Derived, not enumerated: probe every ignorable mark
  // after every base in the region where combining marks carry primary weight.
  const CONTRACTION_BASE_LIMIT = 0x1200; // Latin .. Arabic Supplement
  const CONTRACTION_MARK_LIMIT = 0x2000;
  const marks = [...ignorable].filter((cp) => cp < CONTRACTION_MARK_LIMIT).map((cp) => String.fromCodePoint(cp));
  const contractions = new Set();
  let frontier = atoms.filter((cp) => cp < CONTRACTION_BASE_LIMIT).map((cp) => String.fromCodePoint(cp));
  // Depth 3 covers base + two marks; each level is seeded only by sequences
  // that already contracted, so it stays small after the first.
  for (let depth = 0; depth < 2; depth += 1) {
    const next = [];
    for (const base of frontier) {
      const baseProbe = "m" + base + "m";
      for (const mark of marks) {
        const seq = base + mark;
        if (cmp("m" + seq + "m", baseProbe) !== 0) {
          contractions.add(seq);
          next.push(seq);
        }
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }

  // (d) Buckets over atoms AND contraction sequences together — a contraction
  // needs a position in the same order, not a special case.
  const units = [...atoms.map((cp) => String.fromCodePoint(cp)), ...contractions];
  const byWeight = units.slice().sort((a, b) => cmp("m" + a + "m", "m" + b + "m"));
  const bucketOf = new Map([[byWeight[0], 0]]);
  let bucket = 0;
  for (let i = 1; i < byWeight.length; i += 1) {
    if (cmp("m" + byWeight[i - 1] + "m", "m" + byWeight[i] + "m") !== 0) bucket += 1;
    bucketOf.set(byWeight[i], bucket);
  }

  // (e) Run-length encode the single-codepoint atoms. Whole scripts collate in
  // codepoint order, so this compresses ~1.09M atoms into ~26k runs.
  const ordered = atoms.slice().sort((a, b) => a - b);
  const bucketRuns = [];
  let runStart = ordered[0];
  let runBucket = bucketOf.get(String.fromCodePoint(ordered[0]));
  let runLength = 1;
  for (let i = 1; i < ordered.length; i += 1) {
    const cp = ordered[i];
    const b = bucketOf.get(String.fromCodePoint(cp));
    if (cp === runStart + runLength && b === runBucket + runLength) {
      runLength += 1;
      continue;
    }
    bucketRuns.push([runStart, runBucket, runLength]);
    runStart = cp;
    runBucket = b;
    runLength = 1;
  }
  bucketRuns.push([runStart, runBucket, runLength]);

  const ignorableRanges = [];
  {
    const list = [...ignorable].sort((a, b) => a - b);
    let lo = list[0];
    let hi = list[0];
    for (let i = 1; i < list.length; i += 1) {
      if (list[i] === hi + 1) {
        hi = list[i];
        continue;
      }
      ignorableRanges.push([lo, hi]);
      lo = list[i];
      hi = list[i];
    }
    ignorableRanges.push([lo, hi]);
  }

  // ICU orders decimal digits numerically regardless of script, and mixes them
  // freely inside one run ("a1<VAI TWO>" collates equal to "a12"). Every such
  // digit lands in the same primary bucket as its ASCII twin, so the ten digit
  // buckets identify them and the offset from zeroBucket IS the digit value.
  const zeroBucket = bucketOf.get("0");
  if (bucketOf.get("9") !== zeroBucket + 9) {
    throw new Error("digit buckets are not contiguous; the digit model needs revisiting");
  }
  const contractionTable = {};
  let maxContractionLength = 0;
  for (const seq of contractions) {
    contractionTable[seq] = bucketOf.get(seq);
    maxContractionLength = Math.max(maxContractionLength, [...seq].length);
  }
  return {
    ignorableRanges,
    expansion,
    bucketRuns,
    zeroBucket,
    contractionTable,
    maxContractionLength,
  };
}

console.error("deriving the collation model...");
const model = buildCollationModel();
const collation = {
  // Bumped when the SHAPE changes; the parity test re-verifies the CONTENT.
  schemaVersion: 1,
  collatorOptions: COLLATOR_OPTIONS,
  zeroBucket: model.zeroBucket,
  maxContractionLength: model.maxContractionLength,
  ignorableRanges: model.ignorableRanges,
  expansions: Object.fromEntries([...model.expansion].map(([cp, v]) => [String(cp), v])),
  contractions: model.contractionTable,
  bucketRuns: model.bucketRuns,
};
console.error(
  `  ignorable ranges ${collation.ignorableRanges.length}, expansions ${model.expansion.size},` +
    ` contractions ${Object.keys(collation.contractions).length} (max len ${model.maxContractionLength}),` +
    ` bucket runs ${collation.bucketRuns.length}`,
);

// ---------------------------------------------------------------------------
// 2. Corpora
// ---------------------------------------------------------------------------

// Deterministic PRNG so a regenerated fixture is reproducible.
function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const REALISTIC = [
  "part.step", "Part.step", "PART.STEP", "part.stp",
  "v2.9.step", "v2.10.step", "v10.1.step", "v2.1.step", "v9.step", "v10.step",
  "001.step", "01.step", "1.step", "a01.step", "a1.step", "a001.step",
  "_x.step", "-x.step", ".x.step", "2 x.step", "2x.step",
  "servo_end_mount.3mf", "servo_end_mount_double.3mf",
  "servo_horn_yoke.3mf", "servo_horn_yoke_double_horn.3mf",
  "a b", "a_b", "a-b", "a.b", "a+b", "a~b", "ab", "a1",
  "sub-a.step", "sub/a.step", "sub_a.step", "sub a.step",
  "A.step", "a.step", "à.step", "B.step", "b.step", "é.step", "e.step", "ünicode.step",
  "Z.step", "z.step", "가.step", "日本語.step", "🙂.step",
  "x_1.step", "x-1.step", "x.1.step",
  "bracket (1).step", "bracket (2).step", "bracket (10).step",
  "assembly-v1.0.0.step", "assembly-v1.0.10.step", "assembly-v1.0.2.step",
  "ß.step", "ss.step", "æ.step", "ae.step", "œ.step", "oe.step",
  "ǆ.step", "dz.step", "ﬁ.step", "fi.step", "Ⅻ.step", "xii.step",
  "Ａ.step", "１.step", "①.step", "².step",
  "Å.step", "Å.step", "café.step", "café.step",
  "", " ", "  ", "0", "00", "000",
  "9".repeat(80) + ".step", "9".repeat(81) + ".step",
  "0".repeat(400) + "1.step",
  "x".repeat(300) + ".step",
];

// The adversarial class the design's own corpus could not express: an
// L1-ignorable BETWEEN TWO DIGITS. Each such character is ignorable in
// isolation yet TERMINATES a numeric run, so "1<SHY>2" sorts BEFORE "12".
// Generated from the derived ignorable ranges, not typed.
function ignorableDigitCases() {
  const out = [];
  const samples = [];
  for (const [lo, hi] of collation.ignorableRanges) {
    samples.push(lo);
    if (hi !== lo) samples.push(hi);
  }
  for (const cp of samples) {
    const ig = String.fromCodePoint(cp);
    out.push("1" + ig + "2", "12", "1" + ig + "0", "10", "9" + ig + "9", "99");
    out.push(ig + "5", "5", "5" + ig, "a" + ig + "b", "ab");
    out.push("v1" + ig + "0.step", "v10.step", "v2.step", "v9.step");
    out.push("x" + ig + "1" + ig + "2", "x12");
  }
  return out;
}

// ICU CONTRACTIONS are the one thing a per-character model cannot express: a
// single character collating equal to a multi-character sequence is an
// expansion (handled), but a multi-character sequence collating as a unit is
// not. Arabic presentation forms are the dense case. Sweep the whole block so
// the residue is MEASURED rather than avoided by a corpus that never looks.
function contractionCandidates() {
  const out = [];
  for (let cp = 0xfb50; cp <= 0xfefc; cp += 1) {
    const ch = String.fromCodePoint(cp);
    if (ch.normalize("NFD") !== ch) continue;
    out.push(ch, "a" + ch, ch + "1", "x" + ch + "y");
    const decomposed = ch.normalize("NFKD");
    if (decomposed !== ch) out.push(decomposed, "a" + decomposed, decomposed + "1", "x" + decomposed + "y");
  }
  // A few other scripts that carry contractions or conjuncts at higher levels.
  for (const ch of ["ᾀ", "ﬅ", "ﬆ", "ǈ", "ǋ", "ǳ", "ĳ", "ŉ", "և", "ﷺ", "ﷻ", "㍿", "㋿"]) {
    out.push(ch, "a" + ch, ch + "1");
  }
  return out;
}

function randomCharacters(count) {
  const rand = mulberry32(0x5eed1234);
  const out = [];
  while (out.length < count) {
    const cp = Math.floor(rand() * (MAX_CODEPOINT + 1));
    if (cp >= 0xd800 && cp <= 0xdfff) continue;
    out.push(String.fromCodePoint(cp));
  }
  return out;
}

const sortCorpus = [
  ...REALISTIC,
  ...ignorableDigitCases(),
  ...contractionCandidates(),
  ...randomCharacters(2000),
];
// Deduplicate while preserving first-seen order: sort stability means the
// pre-sort order is part of the contract, so the corpus order is the fixture.
const sortCorpusUnique = [...new Set(sortCorpus)];
const sortGolden = sortCorpusUnique.slice().sort(cmp);

// A full pairwise sign matrix over a slice, so a same-order-different-signs bug
// cannot hide behind a lucky permutation.
const pairSubset = sortCorpusUnique.slice(0, 400);
const sortPairs = [];
for (const a of pairSubset) {
  for (const b of pairSubset) {
    sortPairs.push(Math.sign(cmp(a, b)));
  }
}

// localeCompare with the same options must agree with the cached collator.
for (const a of pairSubset.slice(0, 60)) {
  for (const b of pairSubset.slice(0, 60)) {
    if (Math.sign(a.localeCompare(b, undefined, COLLATOR_OPTIONS)) !== Math.sign(cmp(a, b))) {
      throw new Error(`cached collator disagrees with localeCompare on ${JSON.stringify([a, b])}`);
    }
  }
}

// ---------------------------------------------------------------------------
// 3. Encoder corpora
// ---------------------------------------------------------------------------

const ENCODER_STRINGS = [
  "", "a", "part.step", "a b", "a+b", "a/b", "a?b", "a#b", "a&b", "a=b",
  "a%b", "a:b", "a;b", "a,b", "a@b", "a$b", "a b(c)*d~e._-!'\"#%&+=/?:@$,;[]{}|\\^`<>",
  "!*'()-._~", "ABCdef0189", "résumé (1).glb", "naïve", "日本語", "한국어",
  "🙂", "a🙂b", "emoji 🙂.stl", "\u00ad", "\u200b", "\u0301", "\ufe0f",
  "\t", "\n", "\r", "\u0000", "\u001f", "\u007f",
  "  leading and trailing  ", "..", ".", "../escape.glb", "a\\b.step",
  "C:\\Windows\\win.ini", "\\\\server\\share\\x.step",
  "space in name.step", "a(1)*'.step", "bad\"name\\x.stl",
  "ümlaut ÄÖÜ.step", "Ω≈ç√∫˜µ", "\u{1F600}\u{1F601}", "x".repeat(300),
];

const BASE36_VALUES = [
  "0", "1", "35", "36", "1295", "1296", "2158", "-1", "-36",
  "1719440100123", "1719440100123456789", "9007199254740993",
  "18446744073709551615", "123456789012345678901234567890",
];

// STRINGS, not number literals: a nanosecond mtime is ~1e18, well past
// Number.MAX_SAFE_INTEGER, so a numeric literal is already a rounded double and
// String() of it prints a shortest-round-trip form that is a DIFFERENT integer
// from the one BigInt() sees. The fixture would then disagree with itself.
const FILE_VERSION_CASES = [
  ["0", "0"], ["1", "1"], ["18", "1719440100123456789"], ["4096", "1000000000"],
  ["123456789", "1756713600123456789"], ["0", "1756713600000000000"],
  ["1099511627776", "1893456000999999999"],
];

const FORM_PAIRS = [
  [["file", "/abs/x.glb"]],
  [["file", "/abs/a b/c.step"], ["v", "18-dl3q2rsq5zpa"]],
  [["file", "/abs/a+b/c~d*e!f'g(h)i.step"]],
  [["file", "/abs/日本語/part.step"], ["v", "0-0"]],
  [["file", "/abs/x&y=z?w#v.step"]],
  [["file", "/abs/🙂.stl"]],
  [["file", ""]],
  [["file", "/abs/résumé (1).glb"], ["v", "1-2"]],
  [["file", "/a b/c%d/e\\f.step"]],
];

// localAssetUrlForPath uses path.resolve, so it is POSIX-only in the fixture.
const ASSET_URL_CASES = [
  ["/abs/x.glb", ""],
  ["/abs/a b/c.step", "18-dl3q2rsq5zpa"],
  ["/abs/a+b/c~d*e!f'g(h)i.step", ""],
  ["/abs/日本語/part.step", "0-0"],
  ["/abs/🙂.stl", "  "],
  ["/abs/./redundant/../x.step", "1-2"],
];

const DECODE_INPUTS = [
  "abc", "a%20b", "a%2Fb", "%E6%97%A5%E6%9C%AC", "%F0%9F%99%82",
  "a+b", "100%25", "%41%42%43", "",
  // These throw in JS and must raise in Python.
  "%zz", "%", "%2", "%C0%AF", "%ED%A0%80", "a%", "%FF", "%E0%80%80",
  "%C2", "%E6%97", "%F0%9F%99",
];

function tryDecode(value) {
  try {
    return { ok: true, value: decodeURIComponent(value) };
  } catch {
    return { ok: false, value: null };
  }
}

// `new URL(target, "http://localhost").pathname` normalises dot segments,
// converts backslashes, strips an authority, and re-percent-encodes part of
// ASCII. urlsplit() does NONE of that, so routing on urlsplit().path would send
// /__cad/../etc/passwd into the API dispatch instead of the SPA. Pin the whole
// behaviour rather than reasoning about the spec.
const URL_TARGETS = [
  "/", "/__cad", "/__cad/", "/__cad/server", "/__cad/catalog",
  "/__cad/../etc/passwd", "/__cad/./asset", "/__cad/%2e%2e/etc",
  "/__cad/%2E%2E/etc", "/__cad/.%2e/etc", "/__cad/%2e./etc", "/__cad/%2e/x",
  "/__tess_cache/%2e%2e%2fescape.tess", "/__tess_cache/..%2Fescape.tess",
  "/__tess_cache/../escape.tess", "/__tess_cache/a.tess",
  "/__cad\\asset", "/__cad//asset", "/%2F__cad/asset",
  "//evil.example/__cad/server", "http://evil.example/__cad/server",
  "https://evil.example:8443/__cad/server",
  "/__cad/asset#frag?file=x", "/a b", "/a\"b", "/a<b>c", "/a`b", "/a{b}c",
  "/a|b", "/a^b", "/a%zz", "/a%2Fb", "/a%00b",
  "/assets/%2e%2e%2f%2e%2e%2fetc%2fpasswd", "/assets/app.js", "/assets/missing.js",
  "/index.html%00.js", "/a/./b/../c", "/../..", "/..", "/.", "/a/..",
  "/a/../..", "/\\/evil", "/;p=1/x", "/a?b?c", "/__cad/asset;x", "/#", "/?",
  "/x#y#z", "/é/x", "/%C3%A9/x", "/Users/someone/models", "/__CAD/server",
  "/__cad/store", "/__cad/nope", "/__cad/export",
];

const QUERY_TARGETS = [
  "/x?file=/tmp/a.step", "/x?file=/tmp/x&file=/etc/passwd",
  "/x?file=&v=1&file=z", "/x?a=1;b=2", "/x?file=%zz", "/x?file=%C0%AF",
  "/x?file=%00", "/x?file=a+b", "/x?file=a%20b", "/x", "/x?", "/x?file",
  "/x?force=1", "/x?force=0", "/x?force=true", "/x?file=/a%2Fb.step",
  "/x?file=%2Fabs%2Fa+b%2Fc.step&v=18-dl3q2rsq5zpa",
  "/x?file=/abs/%F0%9F%99%82.stl", "/x?file=%ED%A0%80",
  "/x?v=1&file=z", "/x?FILE=z", "/x?file=x&asset=artifact",
];
const QUERY_KEYS = ["file", "v", "force", "a", "asset", "FILE"];

const pathPercentEncodeSet = [];
for (let byte = 0x00; byte <= 0x7f; byte += 1) {
  // Control characters cannot ride a real request line; probe the printable
  // range only and record the rest as "unreachable" (-1).
  if (byte < 0x20 || byte === 0x7f) {
    pathPercentEncodeSet.push([byte, null]);
    continue;
  }
  const ch = String.fromCharCode(byte);
  let out;
  try {
    out = new URL("/p" + ch + "q", "http://localhost").pathname;
  } catch {
    out = null;
  }
  pathPercentEncodeSet.push([byte, out]);
}

// ---------------------------------------------------------------------------
// 4. Emit
// ---------------------------------------------------------------------------

const golden = {
  note: "GENERATED by tests/python/packages/cadgen/viewer/golden/gen_golden.mjs. Do not hand-edit.",
  node: process.version,
  encodeUriComponent: ENCODER_STRINGS.map((value) => [value, encodeURIComponent(value)]),
  encodeUrlPath: [
    "part.step", "sub dir/part.step", "a/b/c.step", "日本語/part.step",
    "a b(c)*d~e._-!'.step", "x&y=z/w#v.step", "🙂/x.stl",
  ].map((rel) => [rel, `/${rel.split("/").map((p) => encodeURIComponent(p)).join("/")}`]),
  base36: BASE36_VALUES.map((value) => [value, BigInt(value).toString(36)]),
  fileVersion: FILE_VERSION_CASES.map(([size, mtimeNs]) => [
    size,
    mtimeNs,
    `${BigInt(size).toString(36)}-${BigInt(mtimeNs).toString(36)}`,
  ]),
  formEncode: FORM_PAIRS.map((pairs) => {
    const params = new URLSearchParams();
    for (const [k, v] of pairs) params.set(k, v);
    return [pairs, params.toString()];
  }),
  localAssetUrl: ASSET_URL_CASES.map(([filePath, version]) => {
    const params = new URLSearchParams();
    params.set("file", path.resolve(String(filePath || "")));
    const normalized = String(version || "").trim();
    if (normalized) params.set("v", normalized);
    return [filePath, version, `/__cad/asset?${params.toString()}`];
  }),
  strictDecode: DECODE_INPUTS.map((value) => [value, tryDecode(value)]),
  urlPathname: URL_TARGETS.map((target) => {
    try {
      return [target, new URL(target, "http://localhost").pathname];
    } catch {
      return [target, null];
    }
  }),
  urlQuery: QUERY_TARGETS.map((target) => {
    const params = new URL(target, "http://localhost").searchParams;
    return [target, QUERY_KEYS.map((key) => [key, params.get(key)])];
  }),
  pathPercentEncodeSet,
  sortCorpus: sortCorpusUnique,
  sortGolden,
  sortPairSubset: pairSubset,
  sortPairSigns: sortPairs,
};

fs.writeFileSync(path.join(HERE, "golden.json"), `${JSON.stringify(golden, null, 0)}\n`, "utf8");
fs.writeFileSync(path.join(APP_ROOT, "server", "collation.json"), `${JSON.stringify(collation)}\n`, "utf8");

console.error(`wrote tests/python/packages/cadgen/viewer/golden/golden.json (${sortCorpusUnique.length} sort rows, ${sortPairs.length} pair signs)`);
console.error(`wrote server/collation.json`);

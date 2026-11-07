/**
 * Text as stroke polylines in a permissive font: what the board view lays its labels out with — a
 * pad's number and net name, a via's net (`docs/plot-payload.md`'s `label` items) — so the pane and
 * the headless snapshot draw the same strokes.
 *
 * This is a port of the engine's `cad.engine.formats.kicad.stroke_font` (the same table, the same
 * layout; the Python suite holds the two tables equal). KiCad draws text with its own stroke font
 * (newstroke), which is GPL, so the board's picture draws text with Hershey Simplex instead: the
 * same positions, sizes, rotations, mirroring and justification, different glyphs.
 *
 * Hershey Simplex is one of the Hershey fonts, created by Dr. A. V. Hershey while working at the
 * U.S. National Bureau of Standards, and distributed since 1986 in the format James Hurt
 * (Cognition, Inc.) devised: freely usable for any purpose, provided those two acknowledgements
 * travel with the data and the data is not sold in its original form. `GLYPHS` is the Simplex Roman
 * set for ASCII 32 to 126 in that format, as OpenCV ships it (`hershey_fonts.cpp`): each glyph is
 * two characters for its left and right bearings, then pairs of characters for the points of its
 * strokes, each coordinate the character's code minus `R`, y down, a space between strokes.
 * Capitals stand 21 units tall, from y = -12 to the baseline at y = 9; descenders reach y = 16.
 */

/** ASCII 32 (space) to 126 (`~`), in the Hershey distribution's encoding. */
export const GLYPHS = Object.freeze([
  "JZ", "MWRFRT RYQZR[SZRY", "JZNFNM VFVM",
  "G]OFOb UFUb JQZQ JWZW", "H\\PBP_ TBT_ YIWGTFPFMGKIKKLMMNOOUQWRXSYUYXWZT[P[MZKX", "F^[FYGVHSHPGNFLFJGIIIKKMMMOLPJPHNF [FI[ YTWTUUTWTYV[X[ZZ[X[VYT",
  "E_\\O\\N[MZMYNXPVUTXRZP[L[JZIYHWHUISJRQNRMSKSIRGPFNGMIMKNNPQUXWZY[[[\\Z\\Y", "NVRFRM", "KYVBTDRGPKOPOTPYR]T`Vb",
  "KYNBPDRGTKUPUTTYR]P`Nb", "JZRLRX MOWU WOMU", "E_RIR[ IR[R",
  "MWSZR[QZRYSZS\\R^Q_", "E_IR[R", "MWRYQZR[SZRY",
  "G][BIb", "H\\QFNGLJKOKRLWNZQ[S[VZXWYRYOXJVGSFQF", "H\\NJPISFS[",
  "H\\LKLJMHNGPFTFVGWHXJXLWNUQK[Y[", "H\\MFXFRNUNWOXPYSYUXXVZS[P[MZLYKW", "H\\UFKTZT UFU[",
  "H\\WFMFLOMNPMSMVNXPYSYUXXVZS[P[MZLYKW", "H\\XIWGTFRFOGMJLOLTMXOZR[S[VZXXYUYTXQVOSNRNOOMQLT", "H\\YFO[ KFYF",
  "H\\PFMGLILKMMONSOVPXRYTYWXYWZT[P[MZLYKWKTLRNPQOUNWMXKXIWGTFPF", "H\\XMWPURRSQSNRLPKMKLLINGQFRFUGWIXMXRWWUZR[P[MZLX", "MWRMQNROSNRM RYQZR[SZRY",
  "MWRMQNROSNRM SZR[QZRYSZS\\R^Q_", "F^ZIJRZ[", "E_IO[O IU[U",
  "F^JIZRJ[", "I[LKLJMHNGPFTFVGWHXJXLWNVORQRT RYQZR[SZRY", "DaWNVLTKQKOLNMMOMRNTOUQVTVVUWS WKWSXUYV[V\\U]S]O\\L[JYHWGTFQFNGLHJJILHOHRIUJWLYNZQ[T[WZYY",
  "I[RFJ[ RFZ[ MTWT", "G\\KFK[ KFTFWGXHYJYLXNWOTP KPTPWQXRYTYWXYWZT[K[", "H]ZKYIWGUFQFOGMILKKNKSLVMXOZQ[U[WZYXZV",
  "G\\KFK[ KFRFUGWIXKYNYSXVWXUZR[K[", "H[LFL[ LFYF LPTP L[Y[", "HZLFL[ LFYF LPTP",
  "H]ZKYIWGUFQFOGMILKKNKSLVMXOZQ[U[WZYXZVZS USZS", "G]KFK[ YFY[ KPYP", "NVRFR[",
  "JZVFVVUYTZR[P[NZMYLVLT", "G\\KFK[ YFKT POY[", "HYLFL[ L[X[",
  "F^JFJ[ JFR[ ZFR[ ZFZ[", "G]KFK[ KFY[ YFY[", "G]PFNGLIKKJNJSKVLXNZP[T[VZXXYVZSZNYKXIVGTFPF",
  "G\\KFK[ KFTFWGXHYJYMXOWPTQKQ", "G]PFNGLIKKJNJSKVLXNZP[T[VZXXYVZSZNYKXIVGTFPF SWY]", "G\\KFK[ KFTFWGXHYJYLXNWOTPKP RPY[",
  "H\\YIWGTFPFMGKIKKLMMNOOUQWRXSYUYXWZT[P[MZKX", "JZRFR[ KFYF", "G]KFKULXNZQ[S[VZXXYUYF",
  "I[JFR[ ZFR[", "F^HFM[ RFM[ RFW[ \\FW[", "H\\KFY[ YFK[",
  "I[JFRPR[ ZFRP", "H\\YFK[ KFYF K[Y[", "KYOBOb OBVB ObVb",
  "G]IL[b", "KYUBUb NBUB NbUb", "G]JTROZT JTRPZT",
  "I[J[Z[", "LXPFUL PFOGUL", "I\\XMX[ XPVNTMQMONMPLSLUMXOZQ[T[VZXX",
  "H[LFL[ LPNNPMSMUNWPXSXUWXUZS[P[NZLX", "I[XPVNTMQMONMPLSLUMXOZQ[T[VZXX", "I\\XFX[ XPVNTMQMONMPLSLUMXOZQ[T[VZXX",
  "I[LSXSXQWOVNTMQMONMPLSLUMXOZQ[T[VZXX", "MYWFUFSGRJR[ OMVM", "I\\XMX]W`VaTbQbOa XPVNTMQMONMPLSLUMXOZQ[T[VZXX",
  "I\\MFM[ MQPNRMUMWNXQX[", "NVQFRGSFREQF RMR[", "MWRFSGTFSERF SMS^RaPbNb",
  "IZMFM[ WMMW QSX[", "NVRFR[", "CaGMG[ GQJNLMOMQNRQR[ RQUNWMZM\\N]Q][",
  "I\\MMM[ MQPNRMUMWNXQX[", "I\\QMONMPLSLUMXOZQ[T[VZXXYUYSXPVNTMQM", "H[LMLb LPNNPMSMUNWPXSXUWXUZS[P[NZLX",
  "I\\XMXb XPVNTMQMONMPLSLUMXOZQ[T[VZXX", "KXOMO[ OSPPRNTMWM", "J[XPWNTMQMNNMPNRPSUTWUXWXXWZT[Q[NZMX",
  "MYRFRWSZU[W[ OMVM", "I\\MMMWNZP[S[UZXW XMX[", "JZLMR[ XMR[",
  "G]JMN[ RMN[ RMV[ ZMV[", "J[MMX[ XMM[", "JZLMR[ XMR[P_NaLbKb",
  "J[XMM[ MMXM M[X[", "KYTBQEPHPJQMSOSPORSTSUQWPZP\\Q_Tb", "NVRBRb",
  "KYPBSETHTJSMQOQPURQTQUSWTZT\\S_Pb", "F^IUISJPLONOPPTSVTXTZS[Q ISJQLPNPPQTTVUXUZT[Q[O",
]);

const CAP_TOP = -12;
const BASELINE = 9;
const CAP_HEIGHT = BASELINE - CAP_TOP;
// KiCad's own stroke font puts the gap between two lines of text at about 1.6 times the size.
const LINE_SPACING = 1.62;
// KiCad's italic: a point moves right by this share of its height above the baseline (ITALIC_TILT).
const ITALIC_TILT = 1 / 8;

function decode(glyph) {
  const left = glyph.charCodeAt(0) - 82;
  const right = glyph.charCodeAt(1) - 82;
  const strokes = [];
  let stroke = [];
  for (let index = 2; index < glyph.length;) {
    if (glyph[index] === " ") {
      if (stroke.length) strokes.push(stroke);
      stroke = [];
      index += 1;
      continue;
    }
    stroke.push([glyph.charCodeAt(index) - 82, glyph.charCodeAt(index + 1) - 82]);
    index += 2;
  }
  if (stroke.length) strokes.push(stroke);
  return { left, right, strokes };
}

const DECODED = GLYPHS.map(decode);

/**
 * One character in the font's grid: its bearings (the pen starts at `left` and leaves at `right`)
 * and its strokes, y down, baseline at 9. A character outside ASCII is a box the width of an `X`.
 */
export function glyphStrokes(character) {
  const code = character.codePointAt(0);
  if (code >= 32 && code <= 126) return DECODED[code - 32];
  const { left, right } = DECODED["X".charCodeAt(0) - 32];
  return { left, right, strokes: [[[left + 1, CAP_TOP], [right - 1, CAP_TOP], [right - 1, BASELINE], [left + 1, BASELINE], [left + 1, CAP_TOP]]] };
}

function lineStrokes(line, scaleX, scaleY, tilt) {
  const strokes = [];
  let pen = 0;
  for (const character of line) {
    const { left, right, strokes: glyph } = glyphStrokes(character);
    for (const stroke of glyph) strokes.push(stroke.map(([x, y]) => [(pen + x - left) * scaleX - (y - BASELINE) * scaleY * tilt, y * scaleY]));
    pen += right - left;
  }
  return { width: pen * scaleX, strokes };
}

/**
 * `text` as stroke polylines in millimetres, y down, placed as KiCad places text — the engine's
 * `text_strokes`, point for point.
 *
 * @param {string} text
 * @param {{ size: readonly [number, number], at?: readonly [number, number], angle?: number,
 *   justify?: readonly string[], mirror?: boolean, italic?: boolean }} options
 *   `size` is KiCad's `(size HEIGHT WIDTH)`: a capital stands `HEIGHT` tall, the glyphs `WIDTH /
 *   HEIGHT` as wide as the font draws them. `at` is the anchor the text is justified about: the
 *   centre of the capitals' box unless `justify` names `left`, `right`, `top` or `bottom`. `mirror`
 *   flips it about its anchor's vertical; `angle` is degrees counter-clockwise as seen on the
 *   board, applied last.
 * @returns {[number, number][][]}
 */
export function textStrokes(text, { size, at = [0, 0], angle = 0, justify = [], mirror = false, italic = false }) {
  const height = Number(size[0]);
  const width = Number(size[1]);
  if (!(height > 0)) return [];
  const scaleY = height / CAP_HEIGHT;
  const scaleX = (width > 0 ? width : height) / CAP_HEIGHT;
  const lines = String(text).split("\n");
  const laid = lines.map((line) => lineStrokes(line, scaleX, scaleY, italic ? ITALIC_TILT : 0));
  const lineHeight = height * LINE_SPACING;
  const blockHeight = height + lineHeight * (lines.length - 1);
  let firstCentre = 0;
  if (justify.includes("top")) firstCentre = height / 2;
  else if (justify.includes("bottom")) firstCentre = height / 2 - blockHeight;
  const centreOffset = -(CAP_TOP + BASELINE) / 2 * scaleY;
  const radians = (angle * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const out = [];
  laid.forEach(({ width: lineWidth, strokes }, number) => {
    const shiftX = justify.includes("left") ? 0 : justify.includes("right") ? -lineWidth : -lineWidth / 2;
    const shiftY = centreOffset + firstCentre + number * lineHeight;
    for (const stroke of strokes) {
      out.push(stroke.map(([x, y]) => {
        let lx = x + shiftX;
        const ly = y + shiftY;
        if (mirror) lx = -lx;
        // KiCad's rotation in its y-down frame: counter-clockwise on screen.
        return [at[0] + lx * cos + ly * sin, at[1] - lx * sin + ly * cos];
      }));
    }
  });
  return out;
}

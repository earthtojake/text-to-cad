/**
 * A G-code toolpath, as the viewer draws it: every move as a line segment, the extruding ones
 * grouped into layers. Reads what slicers write for FDM — G0/G1 moves, G2/G3 arcs (I/J centre
 * form), G90/G91 and M82/M83 modes, G92 resets and G20/G21 units — and ignores everything else.
 */

export interface GcodeToolpath {
  /** Extruding segments, two points (six floats) each, in file order. */
  extrude: Float32Array;
  /** The layer (0-based) of each extruding segment; never decreases. */
  extrudeLayer: Uint32Array;
  /** Non-extruding moves, two points each. */
  travel: Float32Array;
  /** Each layer's print height, in mm. */
  layerZ: number[];
  /** How many extruding segments end at or before each layer: layer n draws `layerEnd[n]` of them. */
  layerEnd: number[];
  /** How many travel segments come before the end of each layer, likewise. */
  layerTravelEnd: number[];
  stats: GcodeStats;
}

export interface GcodeStats {
  lines: number;
  layers: number;
  extrudeMoves: number;
  travelMoves: number;
  arcMoves: number;
  /** Filament fed, in mm of E. */
  filamentMm: number;
  /** The extruded extents, in mm; null when nothing extrudes. */
  extents: { min: [number, number, number]; max: [number, number, number] } | null;
}

/** How finely an arc is cut into segments, in mm of arc length. */
const ARC_STEP_MM = 1;
const WORD = /([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))/g;

export function parseGcode(text: string): GcodeToolpath {
  const extrude: number[] = [], extrudeLayer: number[] = [], travel: number[] = [];
  const layerZ: number[] = [], layerEnd: number[] = [], layerTravelEnd: number[] = [];
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  let x = 0, y = 0, z = 0, e = 0;
  let absolute = true, absoluteE = true, scale = 1;
  let extrudeMoves = 0, travelMoves = 0, arcMoves = 0, filament = 0, lines = 0;

  const segment = (x0: number, y0: number, z0: number, x1: number, y1: number, z1: number, extruding: boolean) => {
    if (!extruding) { travel.push(x0, y0, z0, x1, y1, z1); return; }
    // A layer starts where extrusion first happens above the last layer.
    if (layerZ.length === 0 || z1 > layerZ[layerZ.length - 1]! + 1e-6) { layerZ.push(z1); layerEnd.push(extrudeLayer.length); layerTravelEnd.push(0); }
    extrude.push(x0, y0, z0, x1, y1, z1);
    extrudeLayer.push(layerZ.length - 1);
    layerEnd[layerZ.length - 1] = extrudeLayer.length;
    layerTravelEnd[layerZ.length - 1] = travel.length / 6;
    for (const [value, axis] of [[x0, 0], [y0, 1], [z0, 2], [x1, 0], [y1, 1], [z1, 2]] as const) {
      if (value < min[axis]) min[axis] = value;
      if (value > max[axis]) max[axis] = value;
    }
  };

  for (const raw of text.split(/\r?\n/)) {
    lines += 1;
    const line = raw.replace(/;.*$/, "").replace(/\(.*?\)/g, "").trim().toUpperCase();
    if (!line) continue;
    const words = new Map<string, number>();
    for (const [, letter, value] of line.matchAll(WORD)) if (!words.has(letter!)) words.set(letter!, Number(value));
    const g = words.get("G"), m = words.get("M");
    if (m === 82) { absoluteE = true; continue; }
    if (m === 83) { absoluteE = false; continue; }
    if (g === 90) { absolute = true; absoluteE = true; continue; }
    if (g === 91) { absolute = false; absoluteE = false; continue; }
    if (g === 20) { scale = 25.4; continue; }
    if (g === 21) { scale = 1; continue; }
    if (g === 92) {
      if (words.has("X")) x = words.get("X")! * scale;
      if (words.has("Y")) y = words.get("Y")! * scale;
      if (words.has("Z")) z = words.get("Z")! * scale;
      if (words.has("E")) e = words.get("E")! * scale;
      continue;
    }
    if (g !== 0 && g !== 1 && g !== 2 && g !== 3) continue;
    const axis = (letter: string, current: number) => {
      const value = words.get(letter);
      if (value === undefined) return current;
      return absolute ? value * scale : current + value * scale;
    };
    const nx = axis("X", x), ny = axis("Y", y), nz = axis("Z", z);
    let fed = 0;
    if (words.has("E")) {
      const value = words.get("E")! * scale;
      fed = absoluteE ? value - e : value;
      e = absoluteE ? value : e + value;
    }
    const extruding = fed > 0 && g !== 0;
    if (extruding) filament += fed;
    if ((g === 2 || g === 3) && (words.has("I") || words.has("J"))) {
      arcMoves += 1;
      const cx = x + (words.get("I") ?? 0) * scale, cy = y + (words.get("J") ?? 0) * scale;
      const radius = Math.hypot(x - cx, y - cy);
      const start = Math.atan2(y - cy, x - cx);
      let sweep = Math.atan2(ny - cy, nx - cx) - start;
      // G2 turns clockwise, G3 counter-clockwise; an arc back to its start is a full turn.
      if (g === 2 && sweep >= 0) sweep -= 2 * Math.PI;
      if (g === 3 && sweep <= 0) sweep += 2 * Math.PI;
      const steps = Math.max(2, Math.ceil(Math.abs(sweep) * radius / ARC_STEP_MM));
      let px = x, py = y, pz = z;
      for (let step = 1; step <= steps; step++) {
        const t = step / steps, angle = start + sweep * t;
        const qx = step === steps ? nx : cx + radius * Math.cos(angle);
        const qy = step === steps ? ny : cy + radius * Math.sin(angle);
        const qz = z + (nz - z) * t;
        segment(px, py, pz, qx, qy, qz, extruding);
        px = qx; py = qy; pz = qz;
      }
    } else if (nx !== x || ny !== y || nz !== z) {
      if (extruding) extrudeMoves += 1; else travelMoves += 1;
      segment(x, y, z, nx, ny, nz, extruding);
    }
    x = nx; y = ny; z = nz;
  }

  return {
    extrude: new Float32Array(extrude),
    extrudeLayer: new Uint32Array(extrudeLayer),
    travel: new Float32Array(travel),
    layerZ,
    layerEnd,
    layerTravelEnd,
    stats: {
      lines,
      layers: layerZ.length,
      extrudeMoves,
      travelMoves,
      arcMoves,
      filamentMm: Math.round(filament * 100) / 100,
      extents: layerZ.length ? { min, max } : null,
    },
  };
}

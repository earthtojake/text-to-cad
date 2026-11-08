/**
 * The net names KiCad's PCB editor writes along its tracks (`pcb_painter.cpp`'s
 * `renderNetNameForSegment` and its arc branch, `PCB_TRACK::ViewGetLOD`; shown by default, as names
 * on pads and tracks). They are not in the plot: how many a segment carries, and so where they fall,
 * depends on the size of the view, so a renderer lays them out from the track's own path, width and
 * net as it draws it. The engine's snapshot painter follows the same rule (`labels.py`'s
 * `track_labels`), number for number.
 */

/** KiCad's canvas at zoom 1: 91 dots per inch, in CSS pixels per millimetre. */
export const KICAD_PX_PER_MM = 91 / 25.4;
/** A track's net name shows once its width is this many millimetres at KiCad's zoom 1. */
const TRACK_LOD_MM = 4;

/** A net's name as KiCad shows it on copper: its last hierarchical part (`/cpu/CLK` is `CLK`). */
export function shortNetName(net) {
  const text = String(net ?? "");
  return text.slice(text.lastIndexOf("/") + 1);
}

/** Whether a plot item is a track: a copper path carrying a net and a width (not a pour's outline or its hatch). */
export function isTrack(item) {
  return item.t === "path" && Boolean(item.net) && item.w > 0 && !item.closed && !item.pairs;
}

/** The CSS pixels per millimetre a view must show for a track's name to be drawn: KiCad's 4 mm over its width. */
export function trackNameDetail(width) {
  return width > 0 ? (TRACK_LOD_MM * KICAD_PX_PER_MM) / width : Infinity;
}

function normalize90(degrees) {
  let angle = degrees;
  while (angle < -90) angle += 180;
  while (angle > 90) angle -= 180;
  return angle;
}

/** A direction's angle as KiCad's text takes it: degrees counter-clockwise on the board (y down), read between -90 and 90. */
const along = (dx, dy) => normalize90((-Math.atan2(dy, dx) * 180) / Math.PI);

/**
 * A track's names in a view `viewport` millimetres across (`[width, height]`), as KiCad writes them:
 * its short net name, 0.55 of its width tall with a pen a twelfth of it, centred on the track and
 * read along it. A segment carries one at its middle, or, long against the view, one per view it
 * spans at even divisions of it (horizontal against the view's width, vertical its height, slanted
 * the diagonal of its shorter side); an arc one at its middle, along its tangent. A track shorter
 * than its name (a square character a width wide) carries none.
 *
 * @param {{ pts: readonly (readonly [number, number])[], w: number, net: string }} item
 * @param {readonly [number, number]} viewport
 * @returns {{ text: string, at: [number, number], size: [number, number], angle: number, w: number }[]}
 */
export function trackNames(item, viewport) {
  const text = shortNetName(item.net);
  const width = item.w;
  const points = item.pts;
  if (!text || !(width > 0) || !points || points.length < 2) return [];
  const nameSize = text.length * width;
  const label = (at, angle) => ({ text, at, size: [width * 0.55, width * 0.55], angle, w: width / 12 });
  if (points.length === 2) {
    const [[x0, y0], [x1, y1]] = points;
    const dx = x1 - x0;
    const dy = y1 - y0;
    const length = Math.hypot(dx, dy);
    if (length < nameSize) return [];
    const [viewWidth, viewHeight] = viewport;
    let angle = 0;
    let span = viewWidth;
    if (dy !== 0 && dx === 0) {
      angle = 90;
      span = viewHeight;
    } else if (dy !== 0) {
      angle = along(dx, dy);
      span = Math.SQRT2 * Math.min(viewWidth, viewHeight);
    }
    const count = span > 0 ? Math.max(1, Math.round(length / span)) : 1;
    const out = [];
    for (let index = 1; index <= count; index += 1) {
      const share = index / (count + 1);
      out.push(label([x0 + dx * share, y0 + dy * share], angle));
    }
    return out;
  }
  let length = 0;
  for (let index = 1; index < points.length; index += 1) {
    length += Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]);
  }
  if (length < nameSize) return [];
  let walked = 0;
  for (let index = 1; index < points.length; index += 1) {
    const [ax, ay] = points[index - 1];
    const [bx, by] = points[index];
    const step = Math.hypot(bx - ax, by - ay);
    if (step > 0 && walked + step >= length / 2) {
      const share = (length / 2 - walked) / step;
      return [label([ax + (bx - ax) * share, ay + (by - ay) * share], along(bx - ax, by - ay))];
    }
    walked += step;
  }
  return [];
}

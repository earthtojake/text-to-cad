import { DOCUMENT_TYPE_REGISTRY } from '../lib/documentTypes.generated.js';

// A Quick Edit's snapshot packet: what `cad snapshot --job` draws again, every view a prompt carries with
// the person's ink over it. The page makes it, the same for every host, from what the person saw (the views a
// prompt carries, `promptViews`, and the ink, an annotation file's document), what a board's prompt names in it
// (`references`) and the file's address as the message names it (`input`); the message carries it inline, whole.
// Nothing is written and no picture is named: `cad snapshot --job` names each output.
//
// It is shortened as it is made, every number to what the view it was seen in can show and nothing a reader
// outside the page cannot use, so the same views and ink give the same packet on every host, but for `input`.

// A drawing's views (a DXF's, a board's, a schematic's) are its plan view framed as the pane framed it: no 3D
// framing for a job's `output` to pin.
const FLAT_VIEWS = new Set(['drawing', 'plot']);
const flat = type => FLAT_VIEWS.has(DOCUMENT_TYPE_REGISTRY.documentTypes.find(entry => entry.id === type)?.view);
// What a view says of its picture beyond its camera, each as the view has it.
const VIEW_FIELDS = ['display', 'kinematics', 'jointValues', 'animation', 'selection'];
// The fields of a mark a reader outside the page has no use for: its id is the page's, and an area's triangles
// fill an outline the outline alone draws again.
const MARK_DROPPED = new Set(['id', 'triangles', 'outline']);
// A camera rounded to a quarter pixel moves the whole picture by a fraction of one, which its every edge shows: its
// position, target and half height are two decimals finer than its view's ink, a hundredth of a quarter pixel.
const CAMERA_EXTRA_DECIMALS = 2;
// `up` is a direction: four decimals turn it less than a hundredth of a degree.
const UP_DECIMALS = 4;
const WIDTH_DECIMALS = 2;

const object = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const roundTo = (value, decimals) => (decimals === null || !Number.isFinite(value) ? value : Number(value.toFixed(decimals)));
const rounded = (values, decimals) => Array.from(values, value => roundTo(Number(value), decimals));

/**
 * A quarter of a pixel of a view, in its units: its camera's frame height (`2 × orthographicHalfHeight`, at the
 * target for a perspective camera) over its picture's height, in four. Null where the view says neither.
 */
export function quarterPixel(view) {
  const half = Number(view?.camera?.orthographicHalfHeight), height = Number(view?.height);
  return half > 0 && height > 0 && Number.isFinite(half / height) ? (2 * half) / height / 4 : null;
}

/** The decimals a quarter pixel `q` needs: `max(0, ceil(-log10(q)))`; null for no quarter pixel. */
export function pixelDecimals(q) {
  if (!(q > 0) || !Number.isFinite(q)) return null;
  // toFixed's bound: a view a hundredth of a quarter pixel across a hundred decimals deep is no view.
  return Math.min(100, Math.max(0, Math.ceil(-Math.log10(q))));
}

// The selector of a ref into the file, the part after its document's `#`, as `cad inspect` reads it
// (`cadRefs.js`'s `engineFile`): a document in quotes (a path with a space or a `#` in it) is read whole first, and
// a `#` after a quote is a quoted label's own; a ref with no document (a bare selector, a glob, a robot's visual id)
// is the selector itself.
function withinFile(ref) {
  const text = String(ref ?? '').trim();
  if (text.startsWith('"')) {
    for (let end = 1; end < text.length; end += 1) {
      if (text[end] === '\\') end += 1;
      else if (text[end] === '"') return text[end + 1] === '#' ? text.slice(end + 2).trim() : text;
    }
    return text;
  }
  const at = text.indexOf('#');
  return at < 0 || text.slice(0, at).includes('"') ? text : text.slice(at + 1).trim();
}
// Refs as the packet names them, within the file: one a document's (`<file>#<selector>`) as its selector.
const refsWithin = refs => (Array.isArray(refs) ? refs.map(ref => (typeof ref === 'string' ? withinFile(ref) : ref)) : refs);

// What a mark was drawn over, within the file: each touch's ref as its selector, once each, in the order found.
// A touch with no ref (a part by the page's own instance id, `i130`) names nothing outside the page.
function touchedWithin(touches) {
  const found = [];
  for (const touch of touches) {
    const ref = typeof touch === 'string' ? touch : object(touch) && typeof touch.ref === 'string' ? touch.ref : '';
    const selector = ref ? withinFile(ref) : '';
    if (selector && !found.includes(selector)) found.push(selector);
  }
  return found;
}

// A view's display as the packet says it: the parts it hid and isolated by their selectors within the file.
function displayWithin(display) {
  if (!object(display)) return display;
  const out = { ...display };
  for (const field of ['hidden', 'isolated']) if (Array.isArray(out[field])) out[field] = refsWithin(out[field]);
  return out;
}

function cameraOf(camera, decimals) {
  if (!object(camera)) return camera;
  const out = { ...camera };
  for (const field of ['position', 'target']) if (Array.isArray(out[field])) out[field] = rounded(out[field], decimals);
  if (Array.isArray(out.up)) out.up = rounded(out.up, UP_DECIMALS);
  if (Number.isFinite(out.orthographicHalfHeight)) out.orthographicHalfHeight = roundTo(out.orthographicHalfHeight, decimals);
  return out;
}

/**
 * Which of a line's points (x, y, z triples) Douglas–Peucker keeps within `tolerance`: its ends, and each point
 * farther than `tolerance` from the segment between the points kept either side of it, the farthest first. Every
 * point dropped lies within `tolerance` of the line kept. A line whose ends are one point (a loop) is measured
 * from its start, where that segment is.
 * @param {ArrayLike<number>} points
 * @param {number} tolerance
 * @returns {number[]} The kept points' indices, in order.
 */
export function douglasPeucker(points, tolerance) {
  const count = Math.floor(points.length / 3);
  if (count < 3) return Array.from({ length: count }, (_, index) => index);
  const keep = new Uint8Array(count);
  keep[0] = keep[count - 1] = 1;
  const spans = [[0, count - 1]];
  while (spans.length) {
    const [first, last] = spans.pop();
    const ax = points[first * 3], ay = points[first * 3 + 1], az = points[first * 3 + 2];
    const abx = points[last * 3] - ax, aby = points[last * 3 + 1] - ay, abz = points[last * 3 + 2] - az;
    const length2 = abx * abx + aby * aby + abz * abz;
    let farthest = -1, at = -1;
    for (let index = first + 1; index < last; index += 1) {
      const apx = points[index * 3] - ax, apy = points[index * 3 + 1] - ay, apz = points[index * 3 + 2] - az;
      const t = length2 > 0 ? Math.min(1, Math.max(0, (apx * abx + apy * aby + apz * abz) / length2)) : 0;
      const distance = Math.hypot(apx - t * abx, apy - t * aby, apz - t * abz);
      if (distance > farthest) { farthest = distance; at = index; }
    }
    if (at >= 0 && farthest > tolerance) {
      keep[at] = 1;
      spans.push([at, last], [first, at]);
    }
  }
  const kept = [];
  keep.forEach((flag, index) => { if (flag) kept.push(index); });
  return kept;
}

// A mark as the packet carries it, its points to the decimals of the view it was drawn in (`q`, that view's quarter
// pixel): a stroke within half a pixel of its line, each point it keeps with its width; an area its outline alone.
function markOf(mark, q) {
  if (!object(mark)) return mark;
  const out = {};
  for (const [field, value] of Object.entries(mark)) {
    if (MARK_DROPPED.has(field) || value === undefined) continue;
    // The defaults a reader assumes: a mark is opaque, and a stroke open.
    if (field === 'opacity' && (value === 1 || value === null)) continue;
    if (field === 'closed' && value !== true) continue;
    out[field] = value;
  }
  if (!('points' in out)) return out;
  let points = rounded(mark.points, pixelDecimals(q));
  // An area's outline is its first points; the rest are inside it, for its triangles.
  if (mark.kind === 'area' && Number.isInteger(mark.outline) && mark.outline > 0) points = points.slice(0, mark.outline * 3);
  let widths = Array.isArray(mark.widths) || ArrayBuffer.isView(mark.widths) ? rounded(mark.widths, WIDTH_DECIMALS) : null;
  if (mark.kind === 'stroke' && q !== null) {
    const kept = douglasPeucker(points, 2 * q);
    if (kept.length < points.length / 3) {
      if (widths?.length === points.length / 3) widths = kept.map(index => widths[index]);
      points = kept.flatMap(index => points.slice(index * 3, index * 3 + 3));
    }
  }
  out.points = points;
  if (widths) out.widths = widths;
  if (Array.isArray(mark.touches)) out.touches = touchedWithin(mark.touches);
  return out;
}

/**
 * A Quick Edit's snapshot packet, made in the page from what the person saw: a job per view (`views`, each a
 * snapshot job's own words, `annotation/views.js`'s), its camera and what it shows (`display`, `kinematics`,
 * `jointValues`, `animation`, `selection`), a 3D view's `output` framing, and its picture by its label and size
 * (`outputs`, no path: `cad snapshot --job` names each); the board `references` its prompt names; the ink
 * (`annotation`, an annotation file's document), and the parts hidden and isolated in the view it was last drawn
 * in (`hidden`, `isolated`), which `--annotation` leaves out of its stills. `input` is the file's address as the
 * message's `File:` line names it (a path from the workspace, a model's id, a shared model's link); `type` its
 * document type, whose snapshot draws the packet (`cad snapshot`: a drawing's views, a DXF's, a board's and a
 * schematic's, have no 3D framing). Null without a view.
 *
 * Shortened as it is made: each mark's points to a quarter of a pixel of the view it was drawn in (`q`,
 * `quarterPixel`: `pixelDecimals(q)` decimals, its `view`'s, else the last view's), each view's camera two decimals
 * finer (its position, target and half height; `up` to four), a stroke's widths to two, and a stroke within half a pixel (`2q`) of its
 * line (`douglasPeucker`); a mark with no `id`, no `opacity` of 1 or `closed` but true, an area its outline alone
 * (no `outline`, no `triangles`), and what it touches as the selectors it was drawn over within the file, as the
 * parts a view hides and isolates are: never the page's own ids, and never the file's address but in `input`.
 *
 * @param {{ input: string, type: string, views: ReadonlyArray<{ label: string, camera: object | string, width?: number,
 *   height?: number } & Record<string, unknown>>, annotation?: { units?: string, marks: object[] } | null,
 *   references?: readonly string[] | null }} options
 * @returns {object | null}
 */
export function snapshotPacket({ input, type, views, annotation = null, references = null }) {
  if (!Array.isArray(views) || !views.length) return null;
  const drawing = flat(type);
  const jobs = views.map(view => {
    const decimals = pixelDecimals(quarterPixel(view));
    const job = { camera: cameraOf(view.camera, decimals === null ? null : Math.min(100, decimals + CAMERA_EXTRA_DECIMALS)) };
    for (const field of VIEW_FIELDS) {
      if (view[field] != null) job[field] = field === 'display' ? displayWithin(view[field]) : view[field];
    }
    if (!drawing) job.output = { padding: 0, tightFrame: false };
    const output = { label: view.label };
    for (const field of ['width', 'height']) if (view[field] !== undefined) output[field] = view[field];
    job.outputs = [output];
    return job;
  });
  const packet = { input, jobs };
  if (references?.length) packet.references = [...references];
  if (annotation) {
    const last = quarterPixel(views.at(-1));
    const quarterOf = label => {
      const view = label == null ? null : views.find(each => each.label === label);
      return view ? quarterPixel(view) : last;
    };
    packet.annotation = { ...annotation, marks: (annotation.marks ?? []).map(mark => markOf(mark, quarterOf(mark?.view))) };
    Object.assign(packet, drawnIn(annotation, views));
  }
  return packet;
}

/**
 * The parts hidden and isolated in the view the ink was last drawn in, the one `--camera authored` draws (by the
 * label the last mark that names one names), as that view's display says them (`display.hidden`,
 * `display.isolated`), within the file: what `--annotation` leaves out of its stills.
 */
function drawnIn(annotation, views) {
  const label = [...(annotation.marks ?? [])].reverse().find(mark => object(mark) && mark.view)?.view;
  const display = views.find(view => view.label === label)?.display;
  if (!object(display)) return {};
  const found = {};
  for (const field of ['hidden', 'isolated']) if (display[field] != null) found[field] = refsWithin(display[field]);
  return found;
}

// What a packet's text writes as its JSON escape, which only a string can hold: what a single-quoted argument ends at,
// in bash (`'`) and in PowerShell (`'`, and its typographic quotes, U+2018 to U+201B), and every other character
// that is not ASCII, which Windows PowerShell 5.1 pipes to a program as ASCII by default (`'<packet>' | cad
// snapshot --job -`, where its quotes are taken from an argument): a code unit at a time, a surrogate pair as two.
const ESCAPED = /['\u0080-\uffff]/g;

/**
 * A packet as a message carries it: compact JSON, no space, in ASCII alone, with no character a single-quoted
 * argument ends at, so `cad snapshot --job '<packet>'` takes it as it is pasted, in bash and PowerShell
 * alike, and a pipe that speaks ASCII alone carries it whole.
 * @param {object} packet
 */
export function snapshotPacketText(packet) {
  return JSON.stringify(packet).replace(ESCAPED, character => `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

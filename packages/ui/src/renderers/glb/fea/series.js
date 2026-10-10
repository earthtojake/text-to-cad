/**
 * A result's series (`extras.series`, read by `readFeaResult`): its modes, times or frequencies, each
 * frame's fields in attributes of their own. What is shown of it is one frame, chosen by What you
 * see's mode picker (`mode`, an enum over the frames' labels) or its scrubber (`frame`, a number
 * over the frames' values that snaps to them), and this resolves that frame's attributes: the
 * field's colours and the deformation's vector. Frame 0's attributes are the fields' own, so a
 * result with no series, or a viewer that knows none, reads frame 0 as it always did.
 * Pure: no three.js, no React.
 */

/** The deformation's own attribute: the displacement the file baked into its positions. */
export const DISPLACEMENT = "_displacement";

/** A field's name in the series' attribute maps: its view name ("mode_shape"), else its attribute's ("_von_mises": "von_mises"). */
export const fieldName = (field) => field.view || String(field.attribute || "").replace(/^_/, "");

/** Whether the frames' values climb, so a scrubber can run along them; else it runs along their places. */
const ascending = (frames) => frames.every((frame, index) => index === 0 || frame.value > frames[index - 1].value);

/** The place of the frame nearest `value` among `values`. */
function nearest(values, value) {
  let best = 0;
  values.forEach((entry, index) => { if (Math.abs(entry - value) < Math.abs(values[best] - value)) best = index; });
  return best;
}

/** What a scrubber's positions are: each frame's value where they climb, else its place (0, 1, ...). */
export const framePositions = (series) => (ascending(series.frames) ? series.frames.map((frame) => frame.value) : series.frames.map((_, index) => index));

/**
 * The frame shown, by its place: the mode picker's (`mode`, the frame's place as a string), else the
 * scrubber's (`frame`, a position that snaps to the nearest frame), else the series' own default
 * (the peak, mode 1). 0 for a result with no series.
 */
export function activeFrameIndex(result, values = {}) {
  const series = result?.series;
  if (!series) return 0;
  const count = series.frames.length;
  const mode = values.mode === undefined || values.mode === null || values.mode === "" ? NaN : Number(values.mode);
  if (Number.isInteger(mode) && mode >= 0 && mode < count) return mode;
  if (Number.isFinite(values.frame)) return nearest(framePositions(series), values.frame);
  return series.default;
}

/** The attribute that holds a field at this frame: the frame's own for it, else the field's (frame 0's, or a field that is the same in every frame). */
export function frameAttribute(result, field, index) {
  const own = index > 0 ? result?.series?.frames[index]?.attributes[fieldName(field)] : null;
  const geometry = result?.mesh?.geometry;
  return own && (!geometry || geometry.getAttribute(own)) ? own : field.attribute;
}

/** A field as it is at this frame: the same words and range (a per-frame field's range spans every frame), read from that frame's attribute. */
export function fieldAtFrame(result, field, index) {
  const attribute = frameAttribute(result, field, index);
  return attribute === field.attribute ? field : { ...field, attribute };
}

/**
 * What the model is deformed by at this frame, `{ attribute, imaginary }`: the frame's displacement,
 * else its mode shape, else the displacement the file baked in (frame 0's, which a mode shape is
 * also written as); and a harmonic frame's imaginary part (`displacement_im`), which its Vibrate
 * turns through. `attribute` null where the result carries no vector to deform by (a temperature).
 */
export function deformationAt(result, index) {
  const frame = result?.series?.frames[index] || null;
  const attributes = frame?.attributes || {};
  const has = (name) => Boolean(name && result.mesh?.geometry?.getAttribute(name)?.itemSize === 3);
  const own = index > 0 ? [attributes.displacement, attributes.mode_shape].find(has) : null;
  const attribute = own || (has(DISPLACEMENT) ? DISPLACEMENT : [attributes.displacement, attributes.mode_shape].find(has) || null);
  const imaginary = has(attributes.displacement_im) ? attributes.displacement_im : null;
  return { attribute, imaginary };
}

/**
 * The frame shown and what it resolves to, for the paint pass: `index`, its `frame` (null with no
 * series), the active `field` read from its attribute and the `deformation` to draw.
 */
export function activeFrame(result, values, field) {
  const index = activeFrameIndex(result, values);
  return { index, frame: result?.series?.frames[index] || null, field: field ? fieldAtFrame(result, field, index) : null, deformation: deformationAt(result, index) };
}

/**
 * Two frames and how far between them a playing series is, at `progress` (0 to 1 over all its
 * frames): `{ from, to, weight }`, frames interpolated linearly.
 */
export function framesBetween(result, progress) {
  const count = result?.series?.frames.length || 0;
  if (count < 2) return { from: 0, to: 0, weight: 0 };
  const at = Math.min(Math.max(Number(progress) || 0, 0), 1) * (count - 1);
  const from = Math.min(Math.floor(at), count - 2);
  return { from, to: from + 1, weight: at - from };
}

/** The scrubber's word by what its frames are: Mode, Frequency, Time, or a load stepped in percent. */
function scrubberLabel(series) {
  if (series.kind === "mode") return "Mode";
  if (series.kind === "frequency") return "Frequency";
  return series.unit === "%" ? "Load step" : "Time";
}

/**
 * What You see's control over the series: a mode picker (`mode`, an enum over the frames' labels,
 * opening on the series' default) for a series of modes, else a scrubber (`frame`, a number along
 * the frames' values that snaps to them, its value field saying the frame's label). `own` is a
 * view's control as the file gives it (`label`, `default`: a mode number or a frame value), where a
 * view names one. null for a result with no series.
 */
export function frameControl(result, drives = result?.series?.kind === "mode" ? "mode" : "frame", own = {}) {
  const series = result?.series;
  if (!series) return null;
  const label = typeof own.label === "string" && own.label.trim() ? own.label.trim() : drives === "mode" ? "Mode" : scrubberLabel(series);
  if (drives === "mode") {
    const options = series.frames.map((frame, index) => ({ value: String(index), label: frame.label || `Mode ${index + 1}` }));
    const named = Number.isFinite(own.default) ? series.frames.findIndex((frame) => frame.value === own.default) : -1;
    return { id: "mode", drives: "mode", type: "enum", label, options, defaultValue: String(named >= 0 ? named : series.default) };
  }
  const positions = framePositions(series);
  const opening = Number.isFinite(own.default) ? positions[nearest(positions, own.default)] : positions[series.default];
  const min = positions[0];
  const max = positions[positions.length - 1];
  if (!(min < max)) return null;
  return {
    id: "frame", drives: "frame", type: "number", label, min, max, defaultValue: opening, unit: ascending(series.frames) ? series.unit : "",
    // The positions it snaps to, and what its value field says at each: the frame's label.
    snaps: positions, frameLabels: series.frames.map((frame) => frame.label),
  };
}

/** A scrubber's value snapped to the frame nearest it. */
export function snapFrame(control, value) {
  return control?.snaps?.length ? control.snaps[nearest(control.snaps, Number(value) || 0)] : value;
}

/** What a scrubber's value field says: the label of the frame it stands on, else null (the plain number). */
export function frameText(control, value) {
  if (!control?.snaps?.length) return null;
  return control.frameLabels?.[nearest(control.snaps, Number(value) || 0)] || null;
}

/** The levels a random vibration's RMS fields are shown at: one and three standard deviations. */
export const SIGMA_LEVELS = Object.freeze([1, 3]);

/** Whether a field is an RMS (one standard deviation) field, which the sigma control multiplies. */
export const isRms = (field) => /_rms$/.test(String(field?.attribute || "").replace(/_f\d+$/, ""));

/** The sigma control: 1σ or 3σ, opening on the level the study judges at (`study.sigma`, else 3). null for a result with no RMS field. */
export function sigmaControl(result, own = {}) {
  if (!result.fields.some(isRms)) return null;
  const label = typeof own.label === "string" && own.label.trim() ? own.label.trim() : "Sigma";
  const asked = [own.default, result.study?.sigma].find((value) => SIGMA_LEVELS.includes(value)) ?? 3;
  return { id: "sigma", drives: "sigma", type: "enum", label, options: SIGMA_LEVELS.map((level) => ({ value: String(level), label: `${level}σ` })), defaultValue: String(asked) };
}

/** The multiple a field's values are shown at for the sigma chosen: the level for an RMS field, 1 for any other. */
export function sigmaScale(field, sigma) {
  const level = Number(sigma);
  return isRms(field) && SIGMA_LEVELS.includes(level) ? level : 1;
}

/**
 * The check kinds an FEA result's verdict can judge, in plain words: the table cadgen's analyses
 * share (spec section 6). Each kind says what its headline is when it is the only check (`titles`,
 * by status), the name a check without a label of its own takes (`defaultLabel`), its unit, how a
 * value is written (`figure`), its row line (`line`: its value against its limit), how its value
 * moves with the load the viewer's load control sets (`scaling`: "linear" k times, "inverse" over
 * k, "none" not at all) and the verdict's takeaway line when it is the worst check (`caption`).
 *
 * A check here is the verdict's: the file's check (`kind`, `label`, `value`, `limit`, `unit`, `ratio`,
 * `margin`, `mode`, `band`, `need`, `life`, `reference`) judged at the load shown, with `shown` its
 * value at that load and, for a kind that scales, `times`, how many times this load it takes to
 * reach its limit. Pure data and functions: no three.js, no React.
 */
import { flooredFactor, plainNumber, threeFigures, unbrokenHalves } from "./numbers.js";

const titles = (fails, close, passes) => Object.freeze({ fails, close, passes });
const unitOf = (check, unit) => check.unit || unit;
const plain = (text) => text.replace(/ /g, " ");

/** What this many times the load means: "OK up to 1.6× this load", "OK only to 0.4× this load" (floored, so it never overstates). */
export function loadCaption(times, noun = "this load") {
  return `OK ${times < 1 ? "only to" : "up to"} ${flooredFactor(times)}× ${noun}`;
}

/** A count of cycles in words: "2.1 million", "500 thousand", "800". */
export function cyclesWords(count) {
  const n = Number(count) || 0;
  if (n >= 1e9) return `${plainNumber(n / 1e9)} billion`;
  if (n >= 1e6) return `${plainNumber(n / 1e6)} million`;
  if (n >= 1e3) return `${plainNumber(n / 1e3)} thousand`;
  return String(Math.round(n));
}

const ORDINAL_MODES = Object.freeze(["First", "Second", "Third", "Fourth", "Fifth"]);
/** A mode as a sentence starts with it: "First mode", "Mode 7". */
const modeWords = (mode) => (ORDINAL_MODES[mode - 1] ? `${ORDINAL_MODES[mode - 1]} mode` : `Mode ${mode}`);

/**
 * A limit check's line from its lead word: "Peak 12 g, limit 10 g". Stress and displacement, whose
 * row's label says what they are, drop it in the verdict's row (`bare`: "405 MPa, limit 276 MPa").
 */
const peakLine = (lead, unit, { figure = plainNumber, bareDropsLead = false } = {}) => (check, { bare = false } = {}) => {
  const u = unitOf(check, unit);
  const value = `${figure(check.shown)} ${u}`;
  return unbrokenHalves([bare && bareDropsLead ? value : `${lead} ${value}`, `limit ${figure(check.limit)} ${u}`]);
};

/** A kind whose own sentence is its takeaway (a kind that does not scale with the load). */
const ownSentence = (kind) => (check, context) => plain(kind.line(check, context));

/** The verdict's caption for a kind that scales with the load: how many times this load the weakest takes. */
const loadTakeaway = (check, { times, noun }) => loadCaption(times ?? check.times, noun);

function kind(spec) {
  const entry = { scaling: "none", margin: false, figure: plainNumber, ...spec };
  if (!entry.caption) entry.caption = entry.scaling === "none" ? ownSentence(entry) : loadTakeaway;
  return Object.freeze(entry);
}

/** A band's ends in words: "110–130 Hz". */
const bandWords = (band, unit) => `${plainNumber(band[0])}–${plainNumber(band[1])} ${unit}`;

/** A frequency check: a mode that must stay above a minimum, or a band no mode may sit in (`band`). */
function frequencyLine(check) {
  const unit = unitOf(check, "Hz");
  const f = `${plainNumber(check.shown)} ${unit}`;
  if (check.band) {
    const inside = check.shown >= check.band[0] && check.shown <= check.band[1];
    return unbrokenHalves([`Mode ${check.mode ?? 1} at ${f}`, `${inside ? "inside" : "clear of"} ${bandWords(check.band, unit)}`]);
  }
  return unbrokenHalves([`${modeWords(check.mode ?? 1)} ${f}`, `must stay above ${plainNumber(check.limit)} ${unit}`]);
}

/** A temperature's takeaway: how far under (or over) its limit the hottest point is. */
function temperatureCaption(check) {
  const unit = unitOf(check, "°C");
  const gap = check.limit - check.shown;
  const room = Math.abs(gap) < 1e-9 ? "at its limit" : `${plainNumber(Math.abs(gap))} ${unit} ${gap > 0 ? "under" : "over"} its limit`;
  return `Hottest ${plainNumber(check.shown)} ${unit}, ${room}`;
}

/** A fatigue check: the life against the life needed, else its Goodman factor at the cycles needed. */
function fatigueLine(check) {
  const need = check.need ?? null;
  if (check.life !== null && check.life !== undefined && need !== null) {
    return unbrokenHalves([`Lasts ${cyclesWords(check.life)} cycles`, `needs ${cyclesWords(need)}`]);
  }
  const at = need !== null ? ` at ${cyclesWords(need)} cycles` : "";
  return unbrokenHalves([`Factor ${flooredFactor(check.shown)}${at}`, `needs ${plainNumber(check.margin ?? check.limit)}`]);
}

export const CHECK_KINDS = Object.freeze({
  // The peak von Mises stress against the yield; how far it is from yield is the safety factor.
  stress: kind({
    titles: titles("Too weak", "Close to the limit", "Strong enough"), defaultLabel: "Strength", unit: "MPa", scaling: "linear", margin: true,
    line: peakLine("Peak", "MPa", { bareDropsLead: true }),
  }),
  displacement: kind({
    titles: titles("Moves too much", "Close to the limit", "Stiff enough"), defaultLabel: "Displacement", unit: "mm", scaling: "linear",
    // A displacement keeps three figures: its limit is often under a millimetre, and 1.04 is not 1.
    figure: threeFigures, line: peakLine("Moves", "mm", { figure: threeFigures, bareDropsLead: true }),
  }),
  // A mode that must stay above a minimum (`min_Hz`), or a band to stay out of (`avoid_Hz`).
  frequency: kind({
    titles: titles("Vibrates too low", "Close to the limit", "Clear of vibration"),
    bandTitles: titles("Resonates in the band", "Close to the band", "Clear of the band"),
    defaultLabel: "Vibration", unit: "Hz", line: frequencyLine,
  }),
  // The load factor λ against the margin asked for: its ratio is 1/λ, so it is used up as the load grows.
  buckling: kind({
    titles: titles("Buckles", "Close to buckling", "Won't buckle"), defaultLabel: "Buckling", unit: "×", scaling: "inverse", margin: true,
    line: (check, { noun = "this load" } = {}) => unbrokenHalves([`Buckles at ${flooredFactor(check.shown)}× ${noun}`, `needs ${plainNumber(check.margin ?? check.limit)}×`]),
  }),
  temperature: kind({
    titles: titles("Runs too hot", "Close to the limit", "Cool enough"), defaultLabel: "Heat", unit: "°C", signedLimit: true,
    line: peakLine("Hottest", "°C"), caption: temperatureCaption,
  }),
  acceleration: kind({
    titles: titles("Shakes too hard", "Close to the limit", "Within the g limit"), defaultLabel: "Shaking", unit: "g", scaling: "linear",
    line: peakLine("Peak", "g"),
  }),
  // The Goodman factor n at the cycles needed (`need`), against its margin; the life (`life`) where the file says it.
  fatigue: kind({
    titles: titles("Wears out too soon", "Close to the limit", "Lasts long enough"), defaultLabel: "Fatigue life", unit: "", margin: true,
    line: fatigueLine,
  }),
  pressure_drop: kind({
    titles: titles("Too much resistance", "Close to the limit", "Flows freely"), defaultLabel: "Flow resistance", unit: "Pa",
    line: peakLine("Drop", "Pa"),
  }),
  velocity: kind({
    titles: titles("Flows too fast", "Close to the limit", "Slow enough"), defaultLabel: "Flow speed", unit: "m/s",
    line: peakLine("Peak", "m/s"),
  }),
  plastic_strain: kind({
    titles: titles("Bends for good", "Close to the limit", "Springs back"), defaultLabel: "Permanent bend", unit: "%",
    line: (check) => {
      const unit = unitOf(check, "%");
      return unbrokenHalves([`${plainNumber(check.shown)} ${unit} permanent`, `limit ${plainNumber(check.limit)} ${unit}`]);
    },
  }),
  contact_pressure: kind({
    titles: titles("Presses too hard", "Close to the limit", "Within the limit"), defaultLabel: "Contact", unit: "MPa",
    line: peakLine("Peak", "MPa"),
  }),
});

/** Every check kind this viewer can judge; a kind from a newer cadgen is skipped. */
export const FEA_CHECK_KINDS = Object.freeze(Object.keys(CHECK_KINDS));

/** A check's headline when it is the only one, at its status: "Too weak", "Runs too hot", "Resonates in the band". */
export function checkTitle(check, status) {
  const entry = CHECK_KINDS[check.kind];
  return (check.band && entry.bandTitles ? entry.bandTitles : entry.titles)[status];
}

/** A check's name: its own label, else the analysis's word for its kind (shock's "Shock"), else the kind's. */
export function checkLabel(check, labels = null) {
  return check.label || labels?.[check.kind] || CHECK_KINDS[check.kind].defaultLabel;
}

/**
 * A check's line, its value against its limit, each half kept whole: "405 MPa, limit 276 MPa" bare
 * (the verdict's row, its label saying what it is), "Peak 405 MPa, limit 276 MPa" in a sentence;
 * a kind whose line reads as a sentence alone says it either way ("First mode 85 Hz, must stay above 60 Hz").
 */
export function checkLine(check, { bare = false, noun = "this load" } = {}) {
  return CHECK_KINDS[check.kind].line(check, { bare, noun });
}

/**
 * The verdict's takeaway when this check is the worst: for a kind that scales with the load, how many
 * times this load the weakest check takes (`times`, the least over the checks that scale); for one
 * that does not, the check's own sentence ("Hottest 84 °C, 16 °C under its limit").
 */
export function checkCaption(check, { times = null, noun = "this load" } = {}) {
  return CHECK_KINDS[check.kind].caption(check, { times, noun });
}

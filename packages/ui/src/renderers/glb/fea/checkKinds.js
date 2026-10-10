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

/** A force as people say it: "5 kN", "1.3 kN", "800 N". */
export function forceWords(newtons) {
  const n = Number(newtons) || 0;
  return Math.abs(n) >= 1000 ? `${plainNumber(n / 1000)} kN` : `${plainNumber(n)} N`;
}

/** A time held in hours as a sentence says it: "10,000 h", "250 h", "2.5 h". */
export function hoursWords(hours) {
  const h = Number(hours) || 0;
  return `${h >= 1000 ? Math.round(h).toLocaleString("en-US") : plainNumber(h)} h`;
}

/** A ply's angle as a layup writes it: "0°", "+45°", "−45°" (a true minus). */
export function plyAngle(angle) {
  const value = Number(angle) || 0;
  if (Math.abs(value) < 1e-9) return "0°";
  return `${value > 0 ? "+" : "−"}${plainNumber(Math.abs(value))}°`;
}

/** "Worst ply 3 (+45°), failure index 0.82"; with no ply on the check, "Failure index 0.82, limit 1". */
function plyLine(check) {
  const index = Number(check.shown).toFixed(2);
  if (Number.isInteger(check.ply)) return unbrokenHalves([`Worst ply ${check.ply} (${plyAngle(check.angle)})`, `failure index ${index}`]);
  return unbrokenHalves([`Failure index ${index}`, `limit ${plainNumber(check.limit)}`]);
}

/** "0.8 % creep after 10,000 h, limit 1 %"; with no time, "0.8 % creep, limit 1 %". */
function creepLine(check) {
  const unit = unitOf(check, "%");
  const hours = check.at?.unit === "h" && Number.isFinite(check.at.value) ? ` after ${hoursWords(check.at.value)}` : "";
  return unbrokenHalves([`${plainNumber(check.shown)} ${unit} creep${hours}`, `limit ${plainNumber(check.limit)} ${unit}`]);
}

/** "Peak 84 dB at 500 Hz, limit 80 dB"; with no frequency on the check, "Peak 84 dB, limit 80 dB". */
function soundLine(check) {
  const unit = unitOf(check, "dB");
  const at = Number.isFinite(check.at?.value) ? ` at ${plainNumber(check.at.value)} ${check.at.unit || "Hz"}` : "";
  return unbrokenHalves([`Peak ${plainNumber(check.shown)} ${unit}${at}`, `limit ${plainNumber(check.limit)} ${unit}`]);
}

/** "K 18 MPa√m at the deepest point, toughness 29 MPa√m"; with no point on the check, "K 18 MPa√m, toughness 29 MPa√m". */
function fractureLine(check) {
  const unit = unitOf(check, "MPa√m");
  const at = check.point ? ` at ${check.point}` : "";
  return unbrokenHalves([`K ${plainNumber(check.shown)} ${unit}${at}`, `toughness ${plainNumber(check.limit)} ${unit}`]);
}

/** A speed as a row says it: "12,400 rpm" (three figures from 1,000 up), "850 rpm". */
export function rpmWords(rpm) {
  const value = Number(rpm) || 0;
  if (Math.abs(value) >= 1000) return `${Number(value.toPrecision(3)).toLocaleString("en-US")} rpm`;
  return `${plainNumber(value)} rpm`;
}

/**
 * A critical speed against the operating speeds: "Critical at 12,400 rpm, 14% above the 10,800 rpm top speed",
 * "… 12% below the 8,000 rpm lowest speed", "Critical at 9,200 rpm, inside 0–10,800 rpm"; with no critical in the
 * sweep (no `mode`), "No critical up to 18,000 rpm, 66% above the 10,800 rpm top speed". `limit` is the operating
 * edge the separation is measured from, `reference` the other edge; the percent is floored, so it never overstates.
 */
function criticalLine(check) {
  const other = Number.isFinite(check.reference) ? check.reference : 0;
  const low = Math.min(check.limit, other);
  const high = Math.max(check.limit, other);
  const percent = (gap, edge) => `${Math.floor((100 * gap) / edge + 1e-9)}%`;
  if (!Number.isInteger(check.mode)) {
    return unbrokenHalves([`No critical up to ${rpmWords(check.shown)}`, `${percent(check.shown - high, high)} above the ${rpmWords(high)} top speed`]);
  }
  const at = `Critical at ${rpmWords(check.shown)}`;
  if (check.shown >= low && check.shown <= high) {
    const from = low >= 1000 ? rpmWords(low).replace(/ rpm$/, "") : plainNumber(low);
    return unbrokenHalves([at, `inside ${from}–${rpmWords(high)}`]);
  }
  if (check.shown > high) return unbrokenHalves([at, `${percent(check.shown - high, high)} above the ${rpmWords(high)} top speed`]);
  return unbrokenHalves([at, `${percent(low - check.shown, low)} below the ${rpmWords(low)} lowest speed`]);
}

/** A whirl's damping: "Log decrement 0.08, needs 0.1"; an undamped rotor (0, no `mode`) neither grows nor dies away. */
function stabilityLine(check) {
  if (!Number.isInteger(check.mode) && check.shown === 0) return unbrokenHalves(["No damping modelled", "neither grows nor dies away"]);
  if (!Number.isInteger(check.mode)) return unbrokenHalves(["No whirl in the speed range", `needs ${plainNumber(check.limit)}`]);
  return unbrokenHalves([`Log decrement ${Number(check.shown.toPrecision(2))}`, `needs ${plainNumber(check.limit)}`]);
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
  // The equivalent creep strain at the end of the hold (`at.value`, in hours), against its limit.
  creep_strain: kind({
    titles: titles("Creeps too far", "Close to the limit", "Holds its shape"), defaultLabel: "Creep", unit: "%",
    line: creepLine,
  }),
  // A laminate's worst ply against a failure index of 1 (Tsai-Wu or max stress, the larger): "Worst ply 3 (+45°), failure index 0.82".
  ply_failure: kind({
    titles: titles("A ply fails", "Close to failing", "Every ply holds"), defaultLabel: "Ply failure", unit: "",
    line: plyLine,
  }),
  // The strongest electric field against the field the gap holds (dry air: about 3 kV/mm); it grows with the voltage.
  electric_field: kind({
    titles: titles("Arcs over", "Close to arcing", "Holds the voltage"), defaultLabel: "Arcing", unit: "kV/mm", scaling: "linear",
    line: peakLine("Peak", "kV/mm"),
  }),
  // A bolt's force after loading (its preload plus its share of the load) against its proof load or a limit.
  bolt_load: kind({
    titles: titles("Bolt overloaded", "Close to the limit", "Bolt holds"), defaultLabel: "Bolt load", unit: "N",
    line: (check) => unbrokenHalves([`Bolt ${forceWords(check.shown)}`, `limit ${forceWords(check.limit)}`]),
  }),
  // The clamp a bolted joint has lost against what it had to lose: all of it, and the faces open.
  joint_separation: kind({
    titles: titles("Joint opens", "Close to opening", "Joint stays shut"), defaultLabel: "Joint separation", unit: "N",
    line: (check) => unbrokenHalves([`Lost ${forceWords(check.shown)}`, `of ${forceWords(check.limit)} clamp`]),
  }),
  // The sideways force a bolted joint carries against what friction holds (μ times its clamp).
  joint_slip: kind({
    titles: titles("Joint slips", "Close to slipping", "Joint holds by friction"), defaultLabel: "Joint slip", unit: "N",
    line: (check) => unbrokenHalves([`Sideways ${forceWords(check.shown)}`, `friction holds ${forceWords(check.limit)}`]),
  }),
  // A gas flow's fastest Mach number (its speed over the local speed of sound) against the most allowed.
  mach: kind({
    titles: titles("Too fast", "Close to the limit", "Within the speed limit"), defaultLabel: "Mach number", unit: "",
    line: (check) => unbrokenHalves([`Peak Mach ${plainNumber(check.shown)}`, `limit ${plainNumber(check.limit)}`]),
  }),
  // The loudest sound pressure level (dB) against the most allowed, and the frequency it peaks at: "Peak 84 dB at 500 Hz, limit 80 dB".
  sound_level: kind({
    titles: titles("Too loud", "Close to the limit", "Quiet enough"), defaultLabel: "Sound", unit: "dB",
    line: soundLine,
  }),
  // A lightened design's share of the part's mass saved, against the least it must save: "Saves 62 % of the mass, needs 25 %".
  mass_saved: kind({
    titles: titles("Barely lighter", "Close", "Much lighter"), defaultLabel: "Mass saved", unit: "%",
    line: (check) => {
      const unit = unitOf(check, "%");
      return unbrokenHalves([`Saves ${plainNumber(check.shown)} ${unit} of the mass`, `needs ${plainNumber(check.limit)} ${unit}`]);
    },
  }),
  // A crack's largest stress intensity K (it grows with the load) against the toughness K_IC: "K 18 MPa√m at the deepest point, toughness 29 MPa√m".
  fracture: kind({
    titles: titles("Crack grows", "Close to the limit", "Crack is safe"), defaultLabel: "Crack", unit: "MPa√m", scaling: "linear", margin: true,
    line: fractureLine,
  }),
  // The cycles a growing crack lasts (Paris's law, to where K reaches K_IC) against the cycles needed.
  crack_life: kind({
    titles: titles("Breaks too soon", "Close to the limit", "Lasts long enough"), defaultLabel: "Crack life", unit: "cycles",
    line: (check) => unbrokenHalves([`Grows to critical in ${cyclesWords(check.shown)} cycles`, `needs ${cyclesWords(check.need ?? check.limit)}`]),
  }),
  // A piezo sensor's signal: the voltage its open electrode makes, against the least it must make ("0.82 V, needs at least 0.5 V").
  voltage: kind({
    titles: titles("Signal too weak", "Close to the limit", "Strong enough signal"), defaultLabel: "Signal", unit: "V",
    line: (check) => {
      const unit = unitOf(check, "V");
      return unbrokenHalves([`${plainNumber(check.shown)} ${unit}`, `needs at least ${plainNumber(check.limit)} ${unit}`]);
    },
  }),
  // The critical speed nearest the operating speeds, against the separation asked (15% by default): a speed, no load moves it.
  critical_speed: kind({
    titles: titles("Runs at a critical speed", "Close to a critical speed", "Clear of critical speeds"), defaultLabel: "Critical speed",
    unit: "rpm", line: criticalLine,
  }),
  // The smallest log decrement of the whirl over the operating speeds: below 0 a whirl grows, under its minimum it is barely damped.
  stability: kind({
    titles: titles("Unstable", "Barely damped", "Stable"), defaultLabel: "Stability", unit: "",
    line: stabilityLine,
  }),
  // The highest a liquid rises inside the part over time, above the inside's floor, against the brim or a limit: "Rises to 42 mm, limit 50 mm";
  // against the tank's own brim (`brim`), "Rises to 42 mm, limit: the brim".
  fill_level: kind({
    titles: titles("Spills over", "Close to the brim", "Stays in"), defaultLabel: "Fill level", unit: "mm",
    line: (check) => {
      const unit = unitOf(check, "mm");
      return unbrokenHalves([`Rises to ${plainNumber(check.shown)} ${unit}`, check.brim ? "limit: the brim" : `limit ${plainNumber(check.limit)} ${unit}`]);
    },
  }),
  // The hardest the fluids press on the part's walls over time, against the most allowed: "Peak 263 Pa, limit 1000 Pa".
  wall_pressure: kind({
    titles: titles("Presses too hard", "Close to the limit", "Within the limit"), defaultLabel: "Wall pressure", unit: "Pa",
    line: peakLine("Peak", "Pa"),
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

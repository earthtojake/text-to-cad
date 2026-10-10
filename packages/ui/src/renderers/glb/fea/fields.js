/**
 * The fields an FEA result can carry, by the attribute that holds them (lower-cased, as GLTFLoader
 * names it, with no frame suffix): the word Show and the colour bar call each by, whether its
 * colours run from its own minimum rather than 0 (`signed`: a temperature) and whether it is a power
 * of ten (`log`: a life in cycles). Pure data: no three.js, no React.
 */

const field = (word, { signed = false, log = false } = {}) => Object.freeze({ word, signed, log });

export const FIELDS = Object.freeze({
  _von_mises: field("Stress"),
  _displacement: field("Displacement"),
  _von_mises_peak: field("Peak stress"),
  _displacement_peak: field("Peak displacement"),
  _temperature: field("Temperature", { signed: true }),
  _heat_flux: field("Heat flow"),
  _mode_shape: field("Mode shape"),
  _life: field("Life", { log: true }),
  _fatigue_factor: field("Fatigue margin"),
  _pressure: field("Pressure", { signed: true }),
  _wall_shear: field("Wall shear"),
  // A gas flow's speed over the local speed of sound, at its wetted walls.
  _mach: field("Mach number"),
  _plastic_strain: field("Plastic strain"),
  _contact_pressure: field("Contact pressure"),
  _creep_strain: field("Creep strain"),
  // A laminate's failure index, the envelope over its plies (1 is the first ply failing).
  _failure_index: field("Failure index"),
  // Electric and magnetic fields: the voltage (signed), the field's strength, the current's, the flux density's.
  _potential: field("Voltage", { signed: true }),
  _electric_field: field("Electric field"),
  _current_density: field("Current density"),
  _magnetic_field: field("Magnetic field"),
  // An AC field's eddy currents (and a fed conductor's current crowding to its skin), their amplitude.
  _eddy_current: field("Eddy current"),
  // Random vibration's RMS fields, one standard deviation; the viewer's sigma control multiplies them.
  _von_mises_rms: field("Stress (1σ)"),
  _displacement_rms: field("Displacement (1σ)"),
});

/** The attribute a field's frames share: "_mode_shape_f3" is "_mode_shape". */
export const fieldBase = (attribute) => String(attribute || "").toLowerCase().replace(/_f\d+$/, "");

/** What a field is, by its attribute (a frame's too); null for one this viewer has no words for. */
export const fieldInfo = (attribute) => FIELDS[fieldBase(attribute)] || null;

/**
 * A field in plain words ("Stress", "Heat flow"), else the name the file gives it. A field the file
 * names for the view (`view`: a mode shape written on the displacement's attribute) is called by that name.
 */
export function fieldWord(field) {
  return (field.view && FIELDS[`_${String(field.view).toLowerCase()}`]?.word) || fieldInfo(field.attribute)?.word || field.name;
}

// The fields in plain words, short enough for the panel's one width, in Show and on the colour bar.
export const FIELD_WORDS = Object.freeze(Object.fromEntries(Object.entries(FIELDS).map(([attribute, entry]) => [attribute, entry.word])));

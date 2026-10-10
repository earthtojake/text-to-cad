import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkCaption, checkLine, checkTitle } from '../checkKinds.js';
import { fieldWord } from '../fields.js';
import { feaControls, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrameIndex } from '../series.js';
import acoustic, { RING, airWords } from './acoustic.js';
import { feaAnalysis } from './index.js';

const plain = (text: string) => text.replace(/[  ]/g, ' ');

// A result as cadgen writes one: the air's modes (a signed pressure shape per mode), or a driven sweep
// (the level in dB and the pressure in Pa per frequency frame), the study echoed under `acoustic`.
function sound(kind: 'modes' | 'response', acousticStudy: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.1, 0, 0, 0.1, 0, 0.006]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 1, 1]), 1));
  const values = kind === 'modes' ? [572, 903] : [100, 500, 900];
  const names = kind === 'modes' ? ['_sound_pressure'] : ['_sound_level', '_sound_pressure'];
  values.forEach((_, index) => names.forEach((name) => {
    geometry.setAttribute(index ? `${name}_f${index}` : name, new BufferAttribute(new Float32Array([1, -0.5, 0]), 1));
  }));
  const fields = kind === 'modes'
    ? [{ attribute: '_SOUND_PRESSURE', name: 'sound pressure (mode shape)', units: '', min: -1, max: 1, attribute_scale: 1, field: 'sound_pressure', signed: true, per_frame: true }]
    : [{ attribute: '_SOUND_LEVEL', name: 'sound pressure level', units: 'dB', min: 60, max: 84, attribute_scale: 1, field: 'sound_level', per_frame: true },
      { attribute: '_SOUND_PRESSURE', name: 'sound pressure amplitude', units: 'Pa', min: 0, max: 0.45, attribute_scale: 1, field: 'sound_pressure', per_frame: true }];
  const series = kind === 'modes'
    ? { kind: 'mode', unit: 'Hz', default: 0, frames: values.map((value, index) => ({ value: index + 1, label: `Mode ${index + 1} · ${value} Hz`,
      attributes: { sound_pressure: index ? `_SOUND_PRESSURE_F${index}` : '_SOUND_PRESSURE' } })) }
    : { kind: 'frequency', unit: 'Hz', default: 2, frames: values.map((value, index) => ({ value, label: `${value} Hz`, attributes: {
      sound_level: index ? `_SOUND_LEVEL_F${index}` : '_SOUND_LEVEL', sound_pressure: index ? `_SOUND_PRESSURE_F${index}` : '_SOUND_PRESSURE' } })) };
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'duct sound', deformation_scale: null, faces: ['#o1.f1', '#o1.f2'],
    analysis: { type: 'acoustic', tier: 3, word: 'Sound', estimate: false, limits: ['Linear acoustics: small sound pressures.'], noun: 'this sound',
      reference_C: null, warnings: [], acoustic: { solve: kind, domain: 'inside' } },
    fields, series,
    study: {
      acoustic: { solve: kind, domain: 'inside', fluid: { name: 'air', density_kg_m3: 1.204, speed_m_s: 343.2 },
        sources: kind === 'modes' ? [] : [{ faces: ['#o1.f1'], velocity_mm_s: 1 }], absorbers: [], open: [], probes: [], ...acousticStudy },
      mesh: { size_mm: 20, order: 2, elements: 114, refined_from_mm: null },
      ...extra,
    },
    checks: kind === 'modes' ? [] : [{ kind: 'sound_level', label: 'Sound', value: 83.9, limit: 80, unit: 'dB', ratio: 1.57, close_at: 0.708,
      status: 'fails', where: { ref: null, at: [499, 20, 20] }, probe: 'end', at: { frame: 2, value: 900, unit: 'Hz' } }],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('acoustic', () => {
  it('is Sound, Tier 3 and linear: the level and the air\'s modes, which no load control moves', () => {
    expect(acoustic).toMatchObject({ name: 'acoustic', tier: 3, word: 'Sound', noun: 'this sound', limitWord: 'Linear', family: null,
      scalesWithLoad: false, checks: ['sound_level', 'frequency'], checkLabels: { frequency: 'Resonance' } });
    expect(feaAnalysis(sound('modes'))).toBe(acoustic);
  });

  it('rings a mode in preview and plays nothing for a sweep', () => {
    expect(acoustic.routine(sound('modes'))).toBe(RING);
    expect(RING).toEqual({ id: 'fea:pulse', label: 'Ring', kind: 'pulse' });
    expect(acoustic.routine(sound('response'))).toBeNull();
  });

  it('opens on the mode picker for modes, and on the Frequency scrubber (at the loudest frame) and the field for a sweep', () => {
    const [mode] = feaControls(sound('modes'));
    expect(mode).toMatchObject({ drives: 'mode', type: 'enum', options: [{ value: '0', label: 'Mode 1 · 572 Hz' }, { value: '1', label: 'Mode 2 · 903 Hz' }] });
    const swept = sound('response');
    const [frequency, field] = feaControls(swept);
    expect(frequency).toMatchObject({ drives: 'frame', label: 'Frequency', min: 100, max: 900, defaultValue: 900, unit: 'Hz' });
    expect(field).toMatchObject({ drives: 'field' });
    expect(field.options.map((option: { label: string }) => option.label)).toEqual(['Sound level', 'Sound pressure']);
    expect(activeFrameIndex(swept)).toBe(2);
  });

  it('calls its fields Sound level and Sound pressure, the pressure signed', () => {
    expect(fieldWord({ attribute: '_sound_level_f2', name: 'sound pressure level' })).toBe('Sound level');
    expect(fieldWord({ attribute: '_sound_pressure', name: 'sound pressure (mode shape)' })).toBe('Sound pressure');
  });

  it('says where the air is, what makes the sound, what soaks it up and where it is listened to', () => {
    const rows = studyRows(sound('response', {
      absorbers: [{ faces: ['#o1.f2'], absorption: 0.3 }], open: [{ faces: ['#o1.f2'] }],
      sources: [{ faces: ['#o1.f1'], velocity_mm_s: 1 }, { point_mm: [0, 0, 10], volume_velocity_m3_s: 1e-6 }],
      probes: [{ label: 'ear', at_mm: [0, 0, 100] }],
    }));
    expect(rows.slice(0, 4).map((row: { label: string }) => row.label)).toEqual(['Air', 'Sound from', 'Soaks up', 'Listening at']);
    expect(rows[0].children[0]).toMatchObject({ label: 'Air inside', hint: 'Sound at 343 m/s' });
    expect(rows[1].children[0]).toMatchObject({ label: 'Speaker face 1 mm/s', faces: ['#o1.f1'], summary: 'A speaker on face 1, moving 1 mm/s' });
    expect(rows[1].children[1]).toMatchObject({ label: 'Point source 1 cm³/s', hint: 'at (0, 0, 10) mm' });
    expect(rows[2].children.map((row: { label: string }) => row.label)).toEqual(['Absorbs 30%', 'Open']);
    expect(rows[3].children[0]).toMatchObject({ label: 'ear', hint: '(0, 0, 100) mm' });
    expect(airWords({ domain: 'outside', fluid: { name: 'water' } })).toBe('Water around it');
    expect(airWords({ domain: 'part' })).toBe('Air filling it');
  });

  it('driven by a harmonic shake, says the part vibrates, where it is held and shaken, and what it is made of', () => {
    const rows = studyRows(sound('response', { from: 'harmonic', sources: [], domain: 'outside' }, {
      material: { name: 'Aluminum 6061-T6', yield_MPa: 276 }, fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }], loads: [],
      excitation: { type: 'base', direction: [0, 0, 1], amplitude_g: 1 }, sweep_Hz: [100, 900], damping_ratio: 0.02,
    }));
    expect(rows.slice(0, 5).map((row: { label: string }) => row.label)).toEqual(['Air', 'Sound from', 'Held at', 'Shaken', 'Made of']);
    expect(rows[0].children[0].label).toBe('Air around it');
    expect(rows[1].children[0].label).toBe('Its own vibration');
    expect(rows[3].children[0].hint).toBe('100 to 900 Hz sweep, 2% damping');
  });

  it('words its sound check with the frequency it peaks at', () => {
    const check = sound('response').checks[0];
    expect(check.at).toMatchObject({ frame: 2, value: 900 });
    expect(['fails', 'close', 'passes'].map((status) => checkTitle(check, status))).toEqual(['Too loud', 'Close to the limit', 'Quiet enough']);
    expect(plain(checkLine({ kind: 'sound_level', shown: 84, limit: 80, unit: 'dB', at: { value: 500, unit: 'Hz' } }))).toBe('Peak 84 dB at 500 Hz, limit 80 dB');
    expect(plain(checkCaption({ kind: 'sound_level', shown: 84, limit: 80, unit: 'dB' }))).toBe('Peak 84 dB, limit 80 dB');
  });
});

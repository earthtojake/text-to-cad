import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { colourBarText } from '../../FeaColourBar.jsx';
import { activeFrameIndex } from '../series.js';
import { heldRows, madeOfRows } from '../setup.js';
import { feaAnalysis } from './index.js';
import multiphase, { TWO_FLUIDS_SETUP, filledRows, fillWords, openingRows, shakeWords } from './multiphase.js';
import { PLAY } from './transient.js';

const LIMIT = 'Laminar (no turbulence model), incompressible; the interface is smeared over a few elements and the walls slide freely; no evaporation, boiling, mixing or foam.';
const FRAMES = [0, 0.0298, 0.0849, 0.3];
const LABELS = ['0 s', '29.8 ms', '84.9 ms', '300 ms'];

// A half-full tank shaken along X, as cadgen writes one: the water fraction and wall pressure on the wetted walls, frame by frame.
function twoFluids(multiphaseStudy: Record<string, unknown> = {}, checks?: unknown[]) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.064, 0, 0, 0, 0, 0.052]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  FRAMES.forEach((_, index) => {
    const suffix = index ? `_f${index}` : '';
    geometry.setAttribute(`_water_fraction${suffix}`, new BufferAttribute(new Float32Array([1, 1, 0]), 1));
    geometry.setAttribute(`_pressure${suffix}`, new BufferAttribute(new Float32Array([245, 240, 0]), 1));
  });
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'tank two fluids', deformation_scale: null, faces: ['#o1.f7', '#o1.f8'], occurrence: '#o1',
    analysis: { type: 'multiphase', tier: 3, word: 'Two fluids', estimate: false, limits: [LIMIT], noun: 'this shake', reference_C: null,
      warnings: [], fill: { fraction: 0.5, level_mm: 25, liquid: 'water', gas: 'air' } },
    fields: [
      { attribute: '_WATER_FRACTION', name: 'water fraction', units: '', min: 0, max: 1, attribute_scale: 1, field: 'water_fraction', per_frame: true },
      { attribute: '_PRESSURE', name: 'wall pressure', units: 'Pa', min: -0.6, max: 263.5, attribute_scale: 1, field: 'pressure', signed: true, per_frame: true },
    ],
    series: { kind: 'time', unit: 's', default: 2, frames: FRAMES.map((value, index) => ({ value, label: LABELS[index], attributes: {
      water_fraction: index ? `_WATER_FRACTION_F${index}` : '_WATER_FRACTION', pressure: index ? `_PRESSURE_F${index}` : '_PRESSURE' } })) },
    study: {
      multiphase: {
        liquid: { name: 'water', density_kg_m3: 998.2, viscosity_Pa_s: 0.001002 }, gas: { name: 'air', density_kg_m3: 1.204, viscosity_Pa_s: 1.81e-5 },
        surface_tension_N_m: 0, fill: { level_mm: 25 }, gravity_m_s2: [0, 0, -9.80665], walls: 'slip', end_s: 1, step_s: null,
        acceleration: { direction: [1, 0, 0], amplitude_g: 0.3, history: { shape: 'half_sine', duration_s: 0.05 }, words: 'half-sine, 50 ms' },
        inlets: [], outlets: [], probes: [], ...multiphaseStudy,
      },
      mesh: { size_mm: 5, order: 2, elements: 2188, refined_from_mm: null }, margin: 2,
    },
    checks: checks ?? [
      { kind: 'fill_level', label: 'Fill level', value: 27.04, limit: 50, unit: 'mm', ratio: 0.5408, close_at: 0.9, status: 'passes',
        where: { ref: null, at: null }, at: { frame: 2, value: 0.0849, unit: 's' } },
      { kind: 'wall_pressure', label: 'Wall pressure', value: 263.5, limit: 1000, unit: 'Pa', ratio: 0.2635, close_at: 0.9, status: 'passes',
        where: { ref: null, at: null }, at: { frame: 1, value: 0.0298, unit: 's' } },
    ],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('multiphase', () => {
  it('is Two fluids, Tier 3: judged by how high the liquid rises and how hard it presses, playing its frames', () => {
    expect(multiphase).toMatchObject({ name: 'multiphase', tier: 3, word: 'Two fluids', noun: 'this shake', limitWord: 'Laminar', family: null,
      scalesWithLoad: false, checks: ['fill_level', 'wall_pressure', 'stress', 'displacement'], displayTitle: 'Flow openings' });
    const result = twoFluids();
    expect(feaAnalysis(result)).toBe(multiphase);
    expect(multiphase.routine(result)).toBe(PLAY);
    expect(multiphase.routine({ series: null })).toBeNull();
  });

  it('opens on the Time scrubber at the highest rise, then the field, water fraction first', () => {
    const result = twoFluids();
    const controls = feaControls(result);
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['frame', 'field']);
    expect(controls[0]).toMatchObject({ label: 'Time', min: 0, max: 0.3, defaultValue: 0.0849, unit: 's', snaps: FRAMES, frameLabels: LABELS });
    expect(controls[1].options).toEqual([{ value: '_water_fraction', label: 'Water fraction' }, { value: '_pressure', label: 'Pressure' }]);
    expect(controls[1].defaultValue).toBe('_water_fraction');
    expect(activeFrameIndex(result)).toBe(2);
    expect(activeFrameIndex(result, { frame: 0.03 })).toBe(1);
    // Its colour bar says the field's word and its scale.
    expect(colourBarText({ attribute: '_water_fraction', name: 'water fraction', units: '', min: 0, max: 1 }).word).toBe('Water fraction');
  });

  it('sets up as filled and shaken, flow in/out, held and made of', () => {
    expect(multiphase.setupGroups).toBe(TWO_FLUIDS_SETUP);
    expect(TWO_FLUIDS_SETUP).toEqual([filledRows, openingRows, heldRows, madeOfRows]);
    const result = twoFluids();
    const rows = studyRows(result);
    expect(rows[0]).toMatchObject({ label: 'Filled' });
    expect(rows[0].children[0]).toMatchObject({ label: 'Half full of water, shaken 0.3 g along X', hint: 'Over time: half-sine, 50 ms',
      summary: 'Filled: half full of water, shaken 0.3 g along X, half-sine, 50 ms' });
    expect(openingRows(result)).toEqual([]);
    const filling = twoFluids({ inlets: [{ opening: 'z_max', velocity_m_s: 0.2, fluid: 'liquid' }], outlets: [{ opening: 'x_max', pressure_Pa: 0 }] });
    expect(openingRows(filling)[0].children.map((row: { label: string }) => row.label))
      .toEqual(['Water in at 0.2 m/s, the high Z side', 'Out at 0 Pa, the high X side']);
    expect([fillWords(0.5), fillWords(0.26, 'oil'), fillWords(0.4), fillWords(Number.NaN, 'oil')])
      .toEqual(['Half full of water', 'A quarter full of oil', '40 % full of water', 'Partly oil']);
    expect([shakeWords({ direction: [0, 1, 0], amplitude_g: 0.5 }), shakeWords(null)]).toEqual(['shaken 0.5 g along Y', '']);
  });

  it('says a completely full inside was solved as single-fluid flow, with no free surface', () => {
    const result = twoFluids({ acceleration: null, inlets: [{ opening: 'x_min', velocity_m_s: 0.05, fluid: 'liquid' }] });
    result.mesh.userData.analysis.fill = { fraction: 1, level_mm: 50, liquid: 'water', gas: 'air' };
    result.analysis.warnings = ['Completely full: solved as single-fluid flow, no free surface'];
    expect(filledRows(result)[0].children[0]).toMatchObject({ label: 'Full of water',
      hint: 'Completely full: solved as single-fluid flow, no free surface' });
  });

  it('says whether it stays in, leading with Laminar, and spills over past the brim', () => {
    expect(feaVerdict(twoFluids()).title).toBe('Passes all checks');
    const verdict = feaVerdict(twoFluids({}, [{ kind: 'fill_level', label: '', value: 27.04, limit: 50, unit: 'mm', ratio: 0.5408, close_at: 0.9,
      status: 'passes', where: { ref: null, at: null }, at: { frame: 2, value: 0.0849, unit: 's' } }]));
    expect(verdict.title).toBe('Stays in');
    expect(verdict.caption).toContain('Laminar · ');
    const spills = feaVerdict(twoFluids({}, [{ kind: 'fill_level', label: '', value: 52, limit: 50, unit: 'mm', ratio: 1.04, close_at: 0.9,
      status: 'fails', where: { ref: null, at: null }, at: { frame: 2, value: 0.0849, unit: 's' } }]));
    expect(spills.title).toBe('Spills over');
    expect(spills.caption.replace(/ /g, ' ')).toContain('Rises to 52 mm, limit 50 mm');
    // Judged against the tank's own brim (no limit_mm), the file says so and the line names the brim.
    const brim = feaVerdict(twoFluids({}, [{ kind: 'fill_level', label: '', value: 52, limit: 50, unit: 'mm', ratio: 1.04, close_at: 0.9,
      status: 'fails', brim: true, where: { ref: null, at: null }, at: { frame: 2, value: 0.0849, unit: 's' } }]));
    expect(brim.caption.replace(/ /g, ' ')).toContain('Rises to 52 mm, limit: the brim');
  });
});

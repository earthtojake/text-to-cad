import { describe, expect, it } from 'vitest';
import { fieldAndDeformation } from '../controls.js';
import { cooledRows, heatedRows, heldRows, keptAtRows, madeOfRows, pushedRows } from '../setup.js';
import { LOAD_RAMP } from './static.js';
import thermalStress from './thermal_stress.js';

const result = {
  fields: [{ attribute: '_von_mises', name: 'von Mises stress' }, { attribute: '_displacement', name: 'displacement' },
    { attribute: '_temperature', name: 'temperature', signed: true }],
  deformationScale: 40,
};

describe('thermal_stress', () => {
  it('is Heat stress: of the static family, its stress and displacement following the load control, "this heat"', () => {
    expect(thermalStress).toMatchObject({ name: 'thermal_stress', tier: 1, word: 'Heat stress', noun: 'this heat', family: 'static',
      scalesWithLoad: true, checks: ['stress', 'displacement'], displayTitle: 'Loads, fixtures and heat' });
    expect(thermalStress.routine(result)).toBe(LOAD_RAMP);
  });

  it('draws its loads and fixtures and its heat', () => {
    expect(thermalStress.markers).toEqual(['load', 'fixture', 'body_load', 'temperature', 'heat', 'convection']);
  });

  it('sets up held at, pushed, then kept at, heated, cooled, made of', () => {
    expect(thermalStress.setupGroups).toEqual([heldRows, pushedRows, keptAtRows, heatedRows, cooledRows, madeOfRows]);
  });

  it('opens on the field over stress, displacement and temperature, and the deformation', () => {
    expect(thermalStress.defaultControls).toBe(fieldAndDeformation);
    const [field, deformation] = thermalStress.defaultControls(result);
    expect(field.options.map((option: { label: string }) => option.label)).toEqual(['Stress', 'Displacement', 'Temperature']);
    expect(deformation).toMatchObject({ drives: 'deformation', defaultValue: 40, max: 160 });
  });
});

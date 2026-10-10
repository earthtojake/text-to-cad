import { describe, expect, it } from 'vitest';
import { FIELDS, FIELD_WORDS, fieldBase, fieldInfo, fieldWord } from './fields.js';

describe('the fields', () => {
  it('name each in plain words, today\'s two as ever', () => {
    expect(FIELD_WORDS._von_mises).toBe('Stress');
    expect(FIELD_WORDS._displacement).toBe('Displacement');
    expect(Object.values(FIELDS).map((entry) => entry.word)).toEqual(['Stress', 'Displacement', 'Peak stress', 'Peak displacement', 'Temperature', 'Heat flow', 'Mode shape', 'Life',
      'Fatigue margin', 'Pressure', 'Wall shear', 'Mach number', 'Plastic strain', 'Contact pressure', 'Creep strain', 'Failure index', 'Voltage', 'Electric field', 'Current density', 'Magnetic field', 'Eddy current', 'Stress (1σ)', 'Displacement (1σ)']);
    // FIELD_WORDS is FIELDS' words, by attribute.
    expect(Object.keys(FIELD_WORDS)).toEqual(Object.keys(FIELDS));
  });

  it('say which run from their own minimum and which are powers of ten', () => {
    expect(Object.keys(FIELDS).filter((attribute) => FIELDS[attribute].signed)).toEqual(['_temperature', '_pressure', '_potential']);
    expect(Object.keys(FIELDS).filter((attribute) => FIELDS[attribute].log)).toEqual(['_life']);
  });

  it('know a frame\'s attribute by its field\'s, and fall back to the file\'s name for one they have no words for', () => {
    expect(fieldBase('_MODE_SHAPE_F3')).toBe('_mode_shape');
    expect(fieldInfo('_mode_shape_f12')?.word).toBe('Mode shape');
    expect(fieldWord({ attribute: '_von_mises', name: 'von Mises stress' })).toBe('Stress');
    expect(fieldWord({ attribute: '_vorticity', name: 'vorticity' })).toBe('vorticity');
    // A field the file names for the view is called by that name, whatever attribute holds it.
    expect(fieldWord({ attribute: '_displacement', name: 'mode shape', view: 'mode_shape' })).toBe('Mode shape');
    expect(fieldWord({ attribute: '_displacement', name: 'displacement', view: 'swirl' })).toBe('Displacement');
  });
});

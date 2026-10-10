import { describe, expect, it } from 'vitest';
import { CHECK_KINDS } from '../checkKinds.js';
import { detailRows, heldRows, madeOfRows, pushedRows } from '../setup.js';
import { ANALYSES, FEA_ANALYSES, analysisNamed, feaAnalysis } from './index.js';
import staticAnalysis, { LOAD_RAMP } from './static.js';

// A result as readFeaResult hands one over, with only what the defaults read.
const result = { fields: [{ attribute: '_von_mises', name: 'von Mises stress' }, { attribute: '_displacement', name: 'displacement' }], deformationScale: 12 };

describe('the analyses', () => {
  it('register every analysis the engine has, each of its own name', () => {
    expect(FEA_ANALYSES).toEqual(['static', 'modal', 'buckling', 'thermal', 'thermal_transient', 'thermal_stress', 'harmonic', 'random_vibration',
      'shock', 'transient', 'fatigue', 'drop', 'cfd', 'impact', 'nonlinear', 'contact', 'bolt', 'creep', 'composite', 'electromagnetic',
      'cfd_turbulent', 'cfd_compressible']);
    for (const name of FEA_ANALYSES) {
      const analysis = ANALYSES[name];
      expect(analysis.name).toBe(name);
      expect(analysis.checks.every((kind: string) => kind in CHECK_KINDS)).toBe(true);
      expect(typeof analysis.word).toBe('string');
      expect(typeof analysis.defaultControls).toBe('function');
    }
  });

  it('read a result with no analysis as static, and one from a newer cadgen as planned, judging every kind', () => {
    expect(feaAnalysis({})).toBe(staticAnalysis);
    expect(feaAnalysis({ analysis: { type: 'static' } })).toBe(staticAnalysis);
    expect(feaAnalysis({ analysis: { type: 'modal' } })).toBe(ANALYSES.modal);
    const newer = analysisNamed('cfd_multiphase', 'Multiphase flow');
    expect(newer).toMatchObject({ name: 'cfd_multiphase', word: 'Multiphase flow', family: null, scalesWithLoad: false });
    expect(newer.checks).toEqual(Object.keys(CHECK_KINDS));
    expect(analysisNamed('cfd_multiphase', 'Multiphase flow')).toBe(newer);
  });

  it('say which follow the load control, which are of the static family, and their words for a stress check', () => {
    expect(FEA_ANALYSES.filter((name) => ANALYSES[name].scalesWithLoad)).toEqual(['static', 'buckling', 'thermal_stress', 'harmonic',
      'random_vibration', 'shock', 'transient', 'drop']);
    expect(FEA_ANALYSES.filter((name) => ANALYSES[name].family === 'static')).toEqual(['static', 'thermal_stress', 'drop']);
    expect(['shock', 'drop', 'random_vibration'].map((name) => ANALYSES[name].checkLabels.stress)).toEqual(['Shock', 'Drop', 'Random vibration']);
    expect(ANALYSES.drop).toMatchObject({ tier: 2, estimate: true, noun: 'this drop' });
    expect(['cfd', 'impact', 'nonlinear', 'contact'].map((name) => ANALYSES[name].tier)).toEqual([3, 3, 3, 3]);
  });

  it('name each one\'s routine: the Load ramp, Buckle, Vibrate, Play over a series, or none', () => {
    const routine = (name: string, series: unknown = null) => ANALYSES[name].routine({ ...result, series })?.label ?? null;
    expect(FEA_ANALYSES.map((name) => [name, routine(name, { frames: [] })])).toEqual([
      ['static', 'Load ramp'], ['modal', 'Vibrate'], ['buckling', 'Buckle'], ['thermal', null], ['thermal_transient', 'Play'],
      ['thermal_stress', 'Load ramp'], ['harmonic', 'Vibrate'], ['random_vibration', null], ['shock', null], ['transient', 'Play'],
      ['fatigue', null], ['drop', 'Load ramp'], ['cfd', null], ['impact', 'Play'], ['nonlinear', 'Play'], ['contact', 'Play'], ['bolt', 'Play'],
      ['creep', 'Play'], ['composite', null], ['electromagnetic', null], ['cfd_turbulent', null], ['cfd_compressible', null]]);
    // Play needs frames to play.
    expect(routine('transient')).toBeNull();
  });

  it('title the Display gate per analysis', () => {
    expect(['static', 'thermal', 'harmonic', 'cfd'].map((name) => ANALYSES[name].displayTitle))
      .toEqual(['Loads and fixtures', 'Heat inputs and temperatures', 'Shaker and fixtures', 'Flow openings']);
  });
});

describe('static', () => {
  it('is today\'s: stress and displacement, by the load, in the static family, its noun "this load"', () => {
    expect(staticAnalysis).toMatchObject({ name: 'static', tier: 1, word: 'Strength', noun: 'this load', family: 'static', scalesWithLoad: true,
      checks: ['stress', 'displacement'], markers: ['load', 'fixture', 'body_load'], displayTitle: 'Loads and fixtures' });
  });

  it('sets up as today: held at, pushed, made of; Details stay the viewer\'s own', () => {
    expect(staticAnalysis.setupGroups).toEqual([heldRows, pushedRows, madeOfRows]);
    expect(staticAnalysis.setupGroups).not.toContain(detailRows);
  });

  it('plays the Load ramp', () => {
    expect(staticAnalysis.routine(result)).toBe(LOAD_RAMP);
    expect(LOAD_RAMP).toEqual({ id: 'fea:load-ramp', label: 'Load ramp', kind: 'load_ramp' });
  });

  it('offers today\'s two controls with no view: a field over every field opening on stress, and the deformation to four times the file\'s', () => {
    expect(staticAnalysis.defaultControls(result)).toEqual([
      { id: 'field', drives: 'field', type: 'enum', label: 'Field', ariaLabel: 'Result field', hideLabel: true,
        options: [{ value: '_von_mises', label: 'Stress' }, { value: '_displacement', label: 'Displacement' }], defaultValue: '_von_mises' },
      { id: 'deformation', drives: 'deformation', type: 'number', label: 'Deformation', ariaLabel: 'Deformation scale',
        labelTitle: 'How much larger than life the displacement is drawn', min: 0, max: 48, step: 0.5, defaultValue: 12, unit: '×' },
    ]);
  });
});

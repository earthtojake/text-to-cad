import { describe, expect, it } from 'vitest';
import { classifyLiveRuntimeObservation } from './live-runtime-observation';
import type { ProjectHostAccessState } from './stores/project-context';

const unavailable: ProjectHostAccessState = {
  kind: 'degraded',
  situation: 'offline',
  recovery: 'automatic',
};

describe('classifyLiveRuntimeObservation', () => {
  it('marks retained observations stale while the project host is unavailable', () => {
    expect(classifyLiveRuntimeObservation(unavailable, ['cached'])).toEqual({
      kind: 'stale',
      value: ['cached'],
    });
  });

  it('marks a never-observed runtime surface unavailable', () => {
    expect(classifyLiveRuntimeObservation(unavailable, undefined)).toEqual({
      kind: 'unavailable',
    });
  });

  it('marks observations live when project host access is ready', () => {
    expect(classifyLiveRuntimeObservation({ kind: 'ready', hostGeneration: 1 }, ['fresh'])).toEqual(
      { kind: 'live', value: ['fresh'] }
    );
  });
});

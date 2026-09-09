import { describe, expect, it } from 'vitest';
import { createPackagedCadSmokePlan, verifyCadRuntimeLock } from './verify-packaged-cad.ts';

describe('packaged CAD smoke plan', () => {
  it('provisions and runs from the packaged Text-to-CAD bundle on Unix', () => {
    const plan = createPackagedCadSmokePlan('/release/resources', '/tmp/smoke', 'linux');
    expect(plan.bundleRoot).toBe('/release/resources/text-to-cad');
    expect(plan.setupScript).toBe(
      '/release/resources/text-to-cad-desktop/tooling/scripts/setup-cad.mjs'
    );
    expect(plan.constraints).toBe(
      '/release/resources/text-to-cad-desktop/tooling/cad-runtime-constraints.txt'
    );
    expect(plan.bundledCadgenSource).toBe('/release/resources/text-to-cad/packages/cadgen');
    expect(plan.python).toBe('/tmp/smoke/runtime/venv/bin/python');
    expect(plan.cacheRoot).toBe('/tmp/smoke/cadgen-cache');
    expect(plan.viewerLauncher).toBe('cadgen.viewer');
    expect(plan.artifact).toBe('/tmp/smoke/workspace/packaged-smoke.step');
    expect(plan.parallelArtifact).toBe(
      '/tmp/smoke/parallel-workspace/packaged-parallel-smoke.step'
    );
  });

  it('accepts only installed packages that match the packaged dependency lock', () => {
    expect(() =>
      verifyCadRuntimeLock(
        [
          'build123d==0.11.1',
          'cadquery-ocp==7.9.3.1.1',
          'colorama==0.4.6',
          'ezdxf==1.4.4',
          'shapely==2.1.2',
          'pip==25.2',
        ].join('\n'),
        [
          'build123d==0.11.1',
          'cadgen @ file:///bundle/cadgen',
          'cadquery-ocp==7.9.3.1.1',
          'colorama==0.4.6',
          'ezdxf==1.4.4',
          'pip==25.2',
          'shapely==2.1.2',
        ].join('\n')
      )
    ).not.toThrow();
  });

  it('rejects drift and newly installed unpinned dependencies', () => {
    const constraints = [
      'build123d==0.11.1',
      'cadquery-ocp==7.9.3.1.1',
      'ezdxf==1.4.4',
      'shapely==2.1.2',
    ].join('\n');
    expect(() =>
      verifyCadRuntimeLock(
        constraints,
        [
          'build123d==0.12.0',
          'cadquery-ocp==7.9.3.1.1',
          'ezdxf==1.4.4',
          'new-transitive==1.0.0',
          'shapely==2.1.2',
        ].join('\n')
      )
    ).toThrow(/dependency lock mismatch.*build123d.*new-transitive/s);
  });

  it('uses the packaged Windows virtual-environment launcher', () => {
    const plan = createPackagedCadSmokePlan('C:\\release\\resources', 'C:\\smoke', 'win32');
    expect(plan.python).toBe('C:\\smoke\\runtime\\venv\\Scripts\\python.exe');
    expect(plan.viewerLauncher).toBe('cadgen.viewer');
    expect(plan.setupScript).toBe(
      'C:\\release\\resources\\text-to-cad-desktop\\tooling\\scripts\\setup-cad.mjs'
    );
  });
});

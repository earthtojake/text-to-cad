import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { stripModelScripts } from '../server/sanitize.ts';

const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

describe('stripModelScripts', () => {
  it('removes animation modules from catalog rows and sidecar files, keeping everything else', () => {
    const sidecar = { schemaVersion: 9, documentHash: 'abc', kinematics: { mates: [] }, animation: { source: 'export const clips = [];' } };
    const sidecarBytes = encode(sidecar);
    const objects = new Map([[sha(sidecarBytes), sidecarBytes]]);
    const index: Record<string, any> = {
      routes: {
        '/__cad/catalog': {
          '/STEP/a.step': { entries: [{ file: '/STEP/a.step', animationHash: 'h', renderModuleUrl: '/x.js', sourceSidecar: { kinematics: { mates: [] }, animation: { source: 'alert(1)' } } }] },
        },
        '/__cad/asset': {
          '/STEP/a.step.json': { object: sha(sidecarBytes), type: 'application/json', bytes: sidecarBytes.byteLength },
          '/STEP/b.step.json': { object: 'f'.repeat(64), type: 'application/json', bytes: 1 },
          '/STEP/a.step': { object: 'e'.repeat(64), type: 'model/step', bytes: 1 },
        },
      },
    };
    const { added } = stripModelScripts(index, objects);

    const entry = index.routes['/__cad/catalog']['/STEP/a.step'].entries[0];
    expect(entry).toEqual({ file: '/STEP/a.step', sourceSidecar: { kinematics: { mates: [] } } });
    expect(added).toHaveLength(1);
    const rewritten = index.routes['/__cad/asset']['/STEP/a.step.json'];
    const served = JSON.parse(new TextDecoder().decode(objects.get(rewritten.object)));
    expect(served).toEqual({ schemaVersion: 9, documentHash: 'abc', kinematics: { mates: [] } });
    expect(rewritten.bytes).toBe(objects.get(rewritten.object)!.byteLength);
    // A sidecar whose bytes are not JSON (here: absent) is not served at all; other files are untouched.
    expect(index.routes['/__cad/asset']['/STEP/b.step.json']).toBeUndefined();
    expect(index.routes['/__cad/asset']['/STEP/a.step'].object).toBe('e'.repeat(64));
  });
});

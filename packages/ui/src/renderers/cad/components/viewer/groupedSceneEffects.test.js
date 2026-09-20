import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import * as THREE from 'three';
import { applyPhotographicStudio, disposePhotographicStudio } from '@hardcore/core/common/photographicStudio.js';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { createFramePresentation } from '../../../kit/viewport/framePresentation.js';

const traverse = traverseModule.default || traverseModule;

function environmentEffect() {
  const source = fs.readFileSync(new URL('../CadViewer.js', import.meta.url), 'utf8');
  const ast = parse(source, { sourceType: 'module', plugins: ['jsx'] });
  let callbackSource;
  traverse(ast, {
    CallExpression(path) {
      if (path.node.callee.type !== 'Identifier' || path.node.callee.name !== 'useEffect') return;
      const callback = path.node.arguments[0];
      if (callback?.type !== 'ArrowFunctionExpression') return;
      const text = source.slice(callback.start, callback.end);
      if (text.includes('const clearEnvironmentResource =') && text.includes('createInspectEnvironmentResource')) {
        assert.equal(callbackSource, undefined, 'one environment effect owns readiness');
        callbackSource = text;
      }
    }
  });
  assert.ok(callbackSource, 'the mounted viewer has an environment owner');
  return Function('scope', `with (scope) { return (${callbackSource})(); }`);
}

for (const group of ['floor', 'background']) {
  test(`${group} with lighting disabled becomes presentable with neutral environment and no PMREM`, () => {
    const run = environmentEffect();
    const events = [];
    const runtime = { THREE, scene: new THREE.Scene(), renderer: {
      toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1,
      shadowMap: { enabled: false }, outputColorSpace: THREE.SRGBColorSpace
    }, modelBounds: { min: [0, 0, 0], max: [10, 10, 10] }, environmentReady: false,
      requestRender: () => events.push('render') };
    const texture = new THREE.Texture();
    const scope = {
      runtimeRef: { current: runtime }, studioScene: () => null,
      renderMode: true, renderConfiguration: { lighting: { enabled: false }, backdrop: { ground: group === 'floor' } },
      photographicLighting: false, inspectHasMaterials: true, INSPECT_ENVIRONMENT_ID: 'neutral',
      createInspectEnvironmentResource: () => ({ texture }),
      applyActivePhotographicStudio: () => { events.push(group); applyPhotographicStudio(THREE, runtime, scope.renderConfiguration); },
      applyActiveSceneBackground: () => { throw new Error('the studio owns the configured backdrop'); },
      viewerAlertChangeRef: { current: () => {} }, viewerTheme: {}, normalizedThemeSettings: { background: {} }
    };
    const canvas = { style: {} };
    const presentation = createFramePresentation({ canvas, renderMode: true });
    run(scope);
    assert.equal(runtime.environmentReady, false, 'wait for the stage chunk');
    assert.equal(presentation.draw({ ...runtime, hasVisibleModel: true }, () => events.push('draw'), { key: 'scene', ready: true }), false);
    scope.studioScene = () => ({
      environmentResourceIdentity: () => { throw new Error('neutral lighting must not request a photographic environment'); },
      createEnvironmentResource: () => { throw new Error('neutral lighting must not build PMREM'); }
    });
    // A stage can predate authored-material hydration. Its initial zero
    // reflection intensity must not override the later neutral environment.
    runtime.scene.environmentIntensity = 0;
    applyPhotographicStudio(THREE, runtime, scope.renderConfiguration);
    events.length = 0;
    run(scope);
    assert.equal(runtime.environmentReady, true);
    assert.equal(runtime.scene.environment, texture);
    assert.equal(runtime.scene.environmentIntensity, 1);
    assert.equal(runtime.environmentResourceIdentity, 'neutral');
    presentation.draw({ ...runtime, hasVisibleModel: true }, () => events.push('draw'), { key: 'scene', ready: true });
    assert.equal(canvas.style.visibility, 'visible');
    assert.deepEqual(events, [group, 'render', 'render', 'draw']);
    scope.applyActivePhotographicStudio();
    assert.equal(runtime.scene.environmentIntensity, 1, 'later stage updates retain neutral reflection fill');
    assert.equal(runtime.photographicStudio.keyLight.visible, false);
    disposePhotographicStudio(runtime);
    texture.dispose();
  });
}

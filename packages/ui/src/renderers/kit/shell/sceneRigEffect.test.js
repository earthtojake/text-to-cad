import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import * as THREE from 'three';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { applySceneRig } from '@text-to-cad/core/lib/viewer/sceneRig.js';
import { normalizeThemeSettings } from '@text-to-cad/core/common/themeSettings.js';

const traverse = traverseModule.default || traverseModule;

// The viewport's look effect (`ShellViewport.jsx`): a scene that brings its own rig (an engine
// document's) is lit by it in place of the theme's lights, its environment the scene's, under its own
// tone curve; any other scene (a STEP model's) is lit by the theme as ever. Read out of the component
// and run against real lights, with a PMREM generator that needs no WebGL.
function lookEffect() {
  const source = fs.readFileSync(new URL('./ShellViewport.jsx', import.meta.url), 'utf8');
  const ast = parse(source, { sourceType: 'module', plugins: ['jsx'] });
  let found;
  traverse(ast, {
    CallExpression(path) {
      if (path.node.callee.type !== 'Identifier' || path.node.callee.name !== 'useEffect') return;
      const callback = path.node.arguments[0];
      if (callback?.type !== 'ArrowFunctionExpression') return;
      const text = source.slice(callback.start, callback.end);
      if (text.includes('applySceneRig(') && text.includes('runtime.hemisphereLight.visible')) {
        assert.equal(found, undefined, 'one effect puts up the look');
        found = text;
      }
    }
  });
  assert.ok(found, 'the viewport has a look effect');
  return Function('scope', `with (scope) { return (${found})(); }`);
}

const THEME_LIGHTS = ['hemisphereLight', 'ambientLight', 'keyLight', 'fillLight', 'rimLight', 'spotLight', 'pointLight'];
const RIG = Object.freeze({
  id: 'engine', ambient: null,
  lights: [{ name: 'key', towards: [0.29, -0.46, 0.84], color: '#ffffff', intensity: 4 }],
  environment: { width: 2, height: 1, data: new Float32Array([1, 1, 1, 1, 2, 2, 2, 1]), intensity: 0.5, rotation: [Math.PI / 2, 0, 0] },
  exposure: 1, toneCurve: 'clamp'
});

function stage() {
  const scene = new THREE.Scene();
  const made = [];
  class PMREMGenerator {
    fromEquirectangular() {
      const target = { texture: new THREE.Texture(), disposed: false, dispose() { this.disposed = true; } };
      made.push(target);
      return target;
    }
    dispose() {}
  }
  const runtime = {
    THREE: { ...THREE, PMREMGenerator }, made, scene, stageGroup: new THREE.Group(), hasVisibleModel: false, softwareRendering: false,
    renderer: { toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1 },
    hemisphereLight: new THREE.HemisphereLight(), ambientLight: new THREE.AmbientLight(), keyLight: new THREE.DirectionalLight(),
    fillLight: new THREE.DirectionalLight(), rimLight: new THREE.DirectionalLight(), spotLight: new THREE.SpotLight(),
    pointLight: new THREE.PointLight(), requestRender() {}
  };
  for (const light of THEME_LIGHTS) scene.add(runtime[light]);
  return runtime;
}

function scopeFor(runtime, sceneRig) {
  return {
    runtimeRef: { current: runtime }, photographicLighting: false, renderMode: false, sceneRig, applySceneRig, THEME_LIGHTS,
    THEME_FLOOR_MODES: { NONE: 'none' }, studioScene: () => null, normalizedThemeSettings: normalizeThemeSettings({}),
    viewerTheme: {}, applySceneBackground: () => {}, syncRuntimeScaledLightingAndShadow: () => {}, updateSpotLightTarget: () => {},
    updateActiveGridHelper: () => {}, updateStageEffects: () => {}, clearGroup: () => {}, applyActivePhotographicStudio: () => {},
    renderShadowMapSizeRef: { current: 2048 }, defaultGridRadius: 100, normalizedSceneScaleMode: 'cad', floorFollowsModel: false,
    resolvedFloorMode: 'none'
  };
}

const rigGroup = runtime => runtime.scene.children.find(child => child.name === 'Scene rig') || null;

test("a scene's own rig lights it in place of the theme's, its environment the scene's, under its own tone curve", () => {
  const run = lookEffect();
  const runtime = stage();
  const theme = normalizeThemeSettings({}).lighting;
  run(scopeFor(runtime, RIG));
  assert.deepEqual(THEME_LIGHTS.filter(light => runtime[light].visible), [], "every theme light off");
  assert.equal(runtime.keyLight.castShadow, false);
  const group = rigGroup(runtime);
  assert.ok(group, "the rig's lights are up");
  assert.deepEqual(group.children.map(light => [light.type, light.intensity]), [['DirectionalLight', 4]]);
  assert.deepEqual([runtime.scene.environment, runtime.scene.environmentIntensity], [runtime.made[0].texture, 0.5],
    "what every surface reflects, the authored finishes among them");
  assert.equal(runtime.renderer.toneMapping, THREE.CustomToneMapping);
  assert.equal(runtime.renderer.toneMappingExposure, 1);
  assert.match(THREE.ShaderChunk.tonemapping_pars_fragment, /CustomToneMapping\( vec3 color \) \{ return saturate\( toneMappingExposure \* color \); \}/);
  // Run again for the same scene (a setting changed): the rig stays up, its exposure over the theme's.
  run(scopeFor(runtime, RIG));
  assert.equal(rigGroup(runtime), group);
  assert.equal(runtime.renderer.toneMappingExposure, 1);
  // The scene's next version brings a rig of the same look: up in the first's place, on its PMREM.
  const next = { ...RIG, id: 'engine, again' };
  run(scopeFor(runtime, next));
  assert.equal(runtime.scene.children.filter(child => child.name === 'Scene rig').length, 1);
  assert.equal(runtime.sceneRig.rig, next);
  assert.deepEqual([runtime.made.length, runtime.made[0].disposed, runtime.scene.environment], [1, false, runtime.made[0].texture]);
  // A scene that brings none in its place: the theme's lights, no environment of the rig's, and the
  // renderer as the theme sets it.
  run(scopeFor(runtime, null));
  assert.equal(rigGroup(runtime), null);
  assert.deepEqual([runtime.made[0].disposed, runtime.scene.environment], [true, null]);
  assert.equal(runtime.renderer.toneMapping, THREE.ACESFilmicToneMapping);
  assert.equal(runtime.renderer.toneMappingExposure, theme.toneMappingExposure);
  assert.deepEqual([runtime.hemisphereLight.visible, runtime.keyLight.visible, runtime.keyLight.castShadow],
    [theme.hemisphere.enabled, theme.directional.enabled, theme.directional.enabled]);
});

test("a STEP model, which brings no rig, is lit by the theme and its renderer left as it was", () => {
  const run = lookEffect();
  const runtime = stage();
  const theme = normalizeThemeSettings({}).lighting;
  run(scopeFor(runtime, null));
  assert.equal(rigGroup(runtime), null);
  assert.equal(runtime.renderer.toneMapping, THREE.ACESFilmicToneMapping);
  assert.equal(runtime.renderer.toneMappingExposure, theme.toneMappingExposure);
  assert.equal(runtime.keyLight.intensity, theme.directional.intensity);
  assert.equal(runtime.ambientLight.visible, theme.ambient.enabled);
});

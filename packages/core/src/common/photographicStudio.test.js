import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  applyPhotographicStudio,
  disposePhotographicStudio
} from "./photographicStudio.js";
import {
  PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES,
  PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT,
  PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY,
  PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX,
  PHOTOGRAPHIC_STUDIO_KEY_DIRECTION,
  PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER
} from "./photographicStudioRig.js";

function rendererStub() {
  const clearColor = new THREE.Color("#334455");
  let clearAlpha = 1;
  return {
    toneMapping: THREE.NoToneMapping,
    toneMappingExposure: 1,
    outputColorSpace: THREE.LinearSRGBColorSpace,
    shadowMap: { enabled: false, type: null },
    getClearColor(target) { target.copy(clearColor); },
    getClearAlpha() { return clearAlpha; },
    setClearColor(color, alpha) {
      clearColor.copy(color);
      clearAlpha = alpha;
    },
    clearState() { return { color: clearColor.getHexString(), alpha: clearAlpha }; }
  };
}

function runtime() {
  return {
    scene: new THREE.Scene(),
    renderer: rendererStub(),
    modelBounds: { min: [-10, -20, -5], max: [30, 40, 15] },
    requestCount: 0,
    requestRender() { this.requestCount += 1; }
  };
}

function configuration(overrides = {}) {
  return {
    exposure: overrides.exposure ?? 0,
    lighting: {
      rotation: overrides.rotation ?? 0,
      size: overrides.size ?? 1,
      fill: overrides.fill ?? 0.25
    },
    backdrop: {
      color: overrides.color ?? "#e7e7e5",
      transparent: overrides.transparent ?? false,
      ground: overrides.ground ?? true,
      groundPlacement: overrides.groundPlacement ?? "origin",
      ...(overrides.groundColor != null ? { groundColor: overrides.groundColor } : {}),
      ...(overrides.groundOpacity != null ? { groundOpacity: overrides.groundOpacity } : {}),
      ...(overrides.groundFinish != null ? { groundFinish: overrides.groundFinish } : {})
    }
  };
}

test("photographic studio applies one scale-stable key, Neutral exposure, and origin-aligned backdrop", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ exposure: 2 }), {
    sceneScale: "cad",
    shadowMapSize: 4096
  });

  assert.equal(value.scene.children.filter((child) => child.name === "cadgen-photographic-studio").length, 1);
  assert.equal(value.renderer.toneMapping, THREE.NeutralToneMapping);
  assert.equal(value.renderer.toneMappingExposure, 4);
  assert.equal(value.renderer.outputColorSpace, THREE.SRGBColorSpace);
  assert.equal(value.renderer.shadowMap.type, THREE.PCFShadowMap);
  assert.equal(state.keyLight.isSpotLight, true);
  assert.ok(state.keyLight.position.clone().sub(state.target.position).normalize().distanceTo(
    new THREE.Vector3(...PHOTOGRAPHIC_STUDIO_KEY_DIRECTION).normalize()
  ) < 1e-12);
  assert.equal(state.keyLight.shadow.mapSize.width, 4096);
  assert.ok(Math.abs(
    state.keyLight.shadow.normalBias
      - (2 * state.keyLight.position.distanceTo(state.target.position)
        * Math.tan(state.keyLight.angle) / 4096)
  ) < 1e-12);
  assert.equal(state.keyLight.shadow.radius, 1.1);
  assert.equal(state.ground.material.isMeshStandardMaterial, true);
  const expectedGroundEmissive = new THREE.Color("#e7e7e5").lerp(
    new THREE.Color(0xffffff),
    PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX
  );
  assert.deepEqual(state.ground.material.emissive.toArray(), expectedGroundEmissive.toArray());
  assert.equal(
    state.ground.material.emissiveIntensity,
    PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY
  );
  assert.equal(state.ground.receiveShadow, false, "its shadow is the soft contact layer");
  assert.ok(state.contactShadow);
  assert.equal(state.ground.position.x, 10);
  assert.equal(state.ground.position.y, 10);
  assert.equal(state.ground.position.z, 0);
  const boundsRadius = Math.hypot(20, 30, 10);
  assert.equal(
    state.ground.scale.x,
    boundsRadius * PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER
  );
  assert.equal(state.ground.scale.y, state.ground.scale.x);
  assert.equal(value.scene.environmentIntensity, 1);
  assert.equal(value.requestCount, 1);
});

test("floor defaults to the lowest point and can stand at the model origin", () => {
  const value = runtime();
  for (const minZ of [-40, 0, 40]) {
    value.modelBounds = { min: [-10, -10, minZ], max: [10, 10, minZ + 20] };
    const originalBounds = structuredClone(value.modelBounds);
    // The floor under the model: either placement changes neither authored geometry nor illumination.
    const state = applyPhotographicStudio(THREE, value, {});
    const keyPosition = state.keyLight.position.clone();
    const keyIntensity = state.keyLight.intensity;
    assert.equal(state.ground.position.z, minZ);
    assert.equal(state.ground.material.transparent, true);
    assert.equal(state.ground.material.opacity, 0.6);
    assert.equal(state.ground.material.side, THREE.DoubleSide);
    assert.equal(state.ground.material.forceSinglePass, true);
    assert.equal(state.ground.material.depthWrite, false);

    const authored = applyPhotographicStudio(THREE, value, configuration({ groundPlacement: "origin" }));
    assert.equal(authored.ground, state.ground);
    assert.equal(authored.ground.position.z, 0);
    // Moving the plane moves nothing else: the key light and the model's own
    // bounds are untouched by either placement.
    assert.ok(authored.keyLight.position.equals(keyPosition));
    assert.equal(authored.keyLight.intensity, keyIntensity);
    assert.deepEqual(value.modelBounds, originalBounds);

    applyPhotographicStudio(THREE, value, configuration({ groundPlacement: "lowest" }));
    assert.equal(state.ground.position.z, minZ);
    applyPhotographicStudio(THREE, value, configuration({ transparent: true }));
    assert.equal(state.ground.position.z, 0);
    assert.equal(state.ground.material.depthWrite, false);
    assert.equal(state.ground.material.polygonOffset, true);
    applyPhotographicStudio(THREE, value, {});
    assert.equal(state.ground.position.z, minZ);
  }
  disposePhotographicStudio(value);
});

test("a floor sized from the rest placement neither grows nor slides when the model moves; only its height follows", () => {
  const value = runtime();
  const rest = { min: [-10, -10, 0], max: [10, 10, 40] };
  const still = applyPhotographicStudio(THREE, value, configuration({ groundPlacement: "lowest" }), { bounds: rest, groundBounds: rest });
  const size = still.ground.scale.x;
  const center = still.ground.position.toArray();
  // An arm swung far out to one side, and a foot below the floor.
  const posed = { min: [-10, -10, -6], max: [90, 10, 40] };
  applyPhotographicStudio(THREE, value, configuration({ groundPlacement: "lowest" }), { bounds: posed, groundBounds: rest });
  assert.equal(still.ground.scale.x, size);
  assert.deepEqual(still.ground.position.toArray(), [center[0], center[1], -6]);
  // Without a rest placement the floor is fitted to the bounds it was given, as before.
  applyPhotographicStudio(THREE, value, configuration({ groundPlacement: "lowest" }), { bounds: posed });
  assert.ok(still.ground.scale.x > size);
  assert.equal(still.ground.position.x, 40);
  disposePhotographicStudio(value);
});

test("valid metre-scale bounds do not inherit CAD's one-unit minimum radius", () => {
  const value = runtime();
  value.modelBounds = { min: [-0.01, -0.01, 0], max: [0.01, 0.01, 0.01] };
  const state = applyPhotographicStudio(THREE, value, configuration(), { sceneScale: "urdf" });
  assert.ok(state.keyLight.position.distanceTo(state.target.position) < 0.1);
  assert.ok(state.keyLight.shadow.normalBias < 0.00005);
});

test("studio illumination is unchanged by model scale or world placement", () => {
  const illuminances = [0.001, 1, 1000].map((scale) => {
    const value = runtime();
    value.modelBounds = {
      min: [90, -70, 25].map((coordinate) => coordinate * scale),
      max: [130, -10, 45].map((coordinate) => coordinate * scale)
    };
    const state = applyPhotographicStudio(THREE, value, configuration());
    return state.keyLight.intensity / state.keyLight.position.distanceToSquared(state.target.position);
  });
  assert.ok(illuminances.every((value) => Math.abs(value - illuminances[0]) < 1e-12));
});

test("shadow normal offset tracks a fitted frustum texel across quality levels", () => {
  const previewRuntime = runtime();
  const finalRuntime = runtime();
  const preview = applyPhotographicStudio(
    THREE,
    previewRuntime,
    configuration(),
    { shadowMapSize: 2048 }
  );
  const final = applyPhotographicStudio(
    THREE,
    finalRuntime,
    configuration(),
    { shadowMapSize: 4096 }
  );

  assert.ok(preview.keyLight.shadow.normalBias > final.keyLight.shadow.normalBias);
  assert.ok(Math.abs(
    preview.keyLight.shadow.normalBias / final.keyLight.shadow.normalBias - 2
  ) < 1e-12);
});

test("photographic rig rejects logarithmic depth because Three drops its contact shadows", () => {
  const value = runtime();
  value.renderer.capabilities = { logarithmicDepthBuffer: true };
  assert.throws(
    () => applyPhotographicStudio(THREE, value, configuration()),
    /without logarithmicDepthBuffer/
  );
  assert.equal(value.photographicStudio, undefined);
});

test("live updates reuse the rig, rotate key and environment together, and resize shadow storage", () => {
  const value = runtime();
  const first = applyPhotographicStudio(THREE, value, configuration(), { shadowMapSize: 2048 });
  const firstKeyPosition = first.keyLight.position.clone();
  let disposedMaps = 0;
  first.keyLight.shadow.map = { dispose() { disposedMaps += 1; } };

  const second = applyPhotographicStudio(
    THREE,
    value,
    configuration({ rotation: 90, size: 3 }),
    { shadowMapSize: 4096 }
  );

  assert.equal(second, first);
  assert.equal(disposedMaps, 1);
  assert.equal(second.keyLight.shadow.map, null);
  assert.equal(second.keyLight.shadow.mapSize.width, 4096);
  assert.equal(second.keyLight.shadow.radius, 2);
  assert.notDeepEqual(second.keyLight.position.toArray(), firstKeyPosition.toArray());
  assert.equal(value.scene.environmentRotation.z, Math.PI / 2);
  assert.equal(value.scene.children.filter((child) => child.name === "cadgen-photographic-studio").length, 1);
});

test("ground fill follows backdrop color without changing studio illumination", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ color: "#224466" }));
  const keyIntensity = state.keyLight.intensity;

  applyPhotographicStudio(THREE, value, configuration({ color: "#663322" }));

  const customColor = new THREE.Color("#663322");
  assert.deepEqual(
    state.ground.material.color.toArray(),
    customColor.clone().multiplyScalar(PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT).toArray()
  );
  const customColorHsl = customColor.getHSL({});
  const customEmissiveHsl = state.ground.material.emissive.getHSL({});
  assert.ok(Math.abs(customEmissiveHsl.h - customColorHsl.h) < 1e-12);
  assert.ok(customEmissiveHsl.l > customColorHsl.l);
  assert.ok(customEmissiveHsl.l - customColorHsl.l < 0.02);
  assert.equal(state.keyLight.intensity, keyIntensity);
  assert.equal(value.scene.environmentIntensity, 1);
});

test("transparent backdrops use a shadow catcher and ground can be removed live", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ transparent: true }));
  assert.equal(value.scene.background, null);
  assert.equal(value.renderer.clearState().alpha, 0);
  assert.equal(state.ground.material.isShadowMaterial, true);

  applyPhotographicStudio(THREE, value, configuration({ transparent: true, ground: false }));
  assert.equal(state.ground, null);
});

test("grouped backdrop alpha and floor work independently with neutral lighting", () => {
  const value = runtime();
  value.renderer.capabilities = { logarithmicDepthBuffer: true };
  value.renderer.toneMappingExposure = 1.16;
  const neutralLight = new THREE.DirectionalLight(0xffffff, 2);
  value.scene.add(neutralLight);
  const recipe = configuration({ groundColor: "#ff8800" });
  recipe.lighting.enabled = false;
  recipe.backdrop.opacity = 0.35;
  const state = applyPhotographicStudio(THREE, value, recipe);
  assert.equal(state.keyLight.visible, false);
  assert.equal(state.shadowMapSize, null, "no shadow storage is configured for a backdrop");
  assert.equal(neutralLight.visible, true);
  assert.equal(value.renderer.toneMapping, THREE.NoToneMapping);
  assert.equal(value.renderer.toneMappingExposure, 1.16);
  assert.equal(value.renderer.shadowMap.enabled, false);
  assert.equal(value.scene.background, null);
  assert.equal(value.renderer.clearState().alpha, 0.35);
  assert.equal(state.ground.material.isMeshStandardMaterial, true);
  applyPhotographicStudio(THREE, value, { ...recipe, backdrop: { ...recipe.backdrop, opacity: 0, transparent: true } });
  assert.equal(state.ground.material.isMeshStandardMaterial, true, "transparent canvas does not replace the independently colored floor");
  assert.equal(value.renderer.clearState().alpha, 0);
  disposePhotographicStudio(value);
  assert.equal(value.scene.children.includes(neutralLight), true);
});

test("disposing the studio removes only owned objects and restores renderer state", () => {
  const value = runtime();
  const unowned = new THREE.Object3D();
  value.scene.add(unowned);
  applyPhotographicStudio(THREE, value, configuration({ exposure: -1 }));
  disposePhotographicStudio(value);

  assert.equal(value.photographicStudio, null);
  assert.equal(value.scene.children.includes(unowned), true);
  assert.equal(value.scene.getObjectByName("cadgen-photographic-studio"), undefined);
  assert.equal(value.renderer.toneMapping, THREE.NoToneMapping);
  assert.equal(value.renderer.toneMappingExposure, 1);
  assert.equal(value.renderer.shadowMap.enabled, false);
  assert.deepEqual(value.renderer.clearState(), { color: "334455", alpha: 1 });
});


test("floor color and opacity update independently while both sides remain visible", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({
    color: "#123456", groundColor: "#ff8800", groundOpacity: 0.8
  }));
  const floor = state.ground;
  const material = floor.material;
  assert.equal(value.scene.background.getHexString(), "123456");
  assert.deepEqual(material.color.toArray(), new THREE.Color("#ff8800")
    .multiplyScalar(PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT).toArray());
  assert.equal(material.opacity, 0.8);
  for (const direction of [-1, 1]) {
    const raycaster = new THREE.Raycaster(
      new THREE.Vector3(0, 0, -direction * 20), new THREE.Vector3(0, 0, direction)
    );
    assert.ok(raycaster.intersectObject(floor).length, "floor visible above and below origin");
  }
  for (const groundOpacity of [0, 1, 0.6]) {
    applyPhotographicStudio(THREE, value, configuration({ groundOpacity }));
    assert.equal(state.ground, floor);
    assert.equal(state.ground.material, material);
    assert.equal(material.opacity, groundOpacity);
    assert.equal(material.depthWrite, false);
    // The floor's shadow is as deep as the floor is opaque.
    assert.equal(state.contactShadow.layer.material.uniforms.uOpacity.value, groundOpacity);
  }
  applyPhotographicStudio(THREE, value, configuration({ transparent: true, groundOpacity: 0.4 }));
  assert.equal(state.ground.material.isShadowMaterial, true);
  assert.equal(state.ground.material.opacity, 0.4);
  assert.equal(state.ground.material.forceSinglePass, true);
  assert.equal(state.ground.receiveShadow, true, "the transparent backdrop's floor is itself the shadow catcher");
  assert.equal(state.contactShadow, null);
  disposePhotographicStudio(value);
});

test("the physical floor carries a soft contact shadow fitted to the rest placement while the studio lights it", () => {
  const value = runtime();
  const rest = { min: [-10, -20, 0], max: [30, 40, 15] };
  const state = applyPhotographicStudio(THREE, value, configuration(), { bounds: rest, groundBounds: rest });
  const contact = state.contactShadow;
  assert.equal(state.ground.receiveShadow, false, "the floor's shadow is the contact layer's, softened");
  assert.equal(state.ground.getObjectByName("studio-contact-shadow-layer"), undefined);
  assert.equal(state.group.getObjectByName("studio-contact-shadow-layer"), contact.layer);
  assert.ok(contact.layer.renderOrder > state.ground.renderOrder, "drawn over the floor");
  assert.equal(contact.layer.material.depthWrite, false);
  assert.equal(contact.layer.visible, true);
  // Its height probe lights nothing: it never joins the scene.
  assert.equal(value.scene.getObjectById(contact.probe.id), undefined);
  // Centred under the rest placement and reaching past its footprint, at the floor.
  assert.equal(contact.layer.position.x, 10);
  assert.equal(contact.layer.position.y, 10);
  assert.equal(contact.layer.position.z, 0);
  assert.ok(contact.layer.scale.x > 60);
  // A pose re-bakes the shadow; it never moves it.
  const scale = contact.layer.scale.x;
  applyPhotographicStudio(THREE, value, configuration(), {
    bounds: { min: [-10, -20, 0], max: [90, 40, 15] }, groundBounds: rest
  });
  assert.equal(contact.layer.scale.x, scale);
  const unlit = configuration();
  unlit.lighting.enabled = false;
  applyPhotographicStudio(THREE, value, unlit, { bounds: rest, groundBounds: rest });
  assert.equal(contact.layer.visible, false, "no key, no cast shadow");
  disposePhotographicStudio(value);
  assert.equal(value.scene.getObjectByName("studio-contact-shadow"), undefined);
});


test("the floor and its shadow are dithered: a dark floor's shallow gradients round to grain, not bands", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ color: "#121315" }));
  const shader = {
    uniforms: {},
    vertexShader: "#include <common>\nvoid main() {\n#include <fog_vertex>\n}",
    fragmentShader: "#include <common>\nvoid main() {\n#include <dithering_fragment>\n}"
  };
  state.ground.material.onBeforeCompile(shader);
  // Up to a level either way, scaled through the floor's blend so it survives at full size.
  assert.match(shader.fragmentShader, /rand\(gl_FragCoord\.xy\)/);
  assert.match(shader.fragmentShader, /255\.0 \* max\(gl_FragColor\.a/);
  assert.doesNotMatch(shader.fragmentShader, /#include <dithering_fragment>/);
  // Its shadow darkens the floor in a pass of its own, rounded again: dithered too.
  assert.match(state.contactShadow.layer.material.fragmentShader, /ditherNoise\(gl_FragCoord\.xy/);
  disposePhotographicStudio(value);
});

test("a snapshot's render scale spreads the floor's dither, and a viewer's floor compiles as it always did", () => {
  // A snapshot at render scale 2 averages four drawn pixels into each pixel it keeps, which
  // quiets one level of noise to half of one and lets the kept pixels band again.
  const snapshot = runtime();
  const state = applyPhotographicStudio(THREE, snapshot, configuration({ color: "#121315" }), { ditherScale: 2 });
  assert.equal(state.ground.material.defines?.STUDIO_DITHER_SCALE, "2.0000", "the floor's noise is drawn twice as wide");
  assert.equal(state.contactShadow.layer.material.defines?.STUDIO_DITHER_SCALE, "2.0000", "and its shadow's");
  const shader = {
    uniforms: {},
    vertexShader: "#include <common>\nvoid main() {\n#include <fog_vertex>\n}",
    fragmentShader: "#include <common>\nvoid main() {\n#include <dithering_fragment>\n}"
  };
  state.ground.material.onBeforeCompile(shader);
  assert.match(shader.fragmentShader, /\* STUDIO_DITHER_SCALE/);
  assert.match(state.contactShadow.layer.material.fragmentShader, /\* STUDIO_DITHER_SCALE/);
  // A viewer shows its pixels as drawn and passes no scale: nothing is defined, so its
  // programs, and its pixels, are the ones they always were; a scale back at 1 is that again.
  const viewer = runtime();
  const viewerState = applyPhotographicStudio(THREE, viewer, configuration({ color: "#121315" }));
  assert.equal(viewerState.ground.material.defines?.STUDIO_DITHER_SCALE, undefined);
  assert.equal(viewerState.contactShadow.layer.material.defines?.STUDIO_DITHER_SCALE, undefined);
  applyPhotographicStudio(THREE, snapshot, configuration({ color: "#121315" }), { ditherScale: 1 });
  assert.equal(state.ground.material.defines?.STUDIO_DITHER_SCALE, undefined);
  assert.equal(state.contactShadow.layer.material.defines?.STUDIO_DITHER_SCALE, undefined);
  disposePhotographicStudio(snapshot);
  disposePhotographicStudio(viewer);
});

test("a matte floor allocates nothing of a glossy one's reflection, which goes again once the floor is matte or unlit", () => {
  const value = runtime();
  const floorShader = (material) => {
    const shader = {
      uniforms: {},
      vertexShader: "#include <common>\nvoid main() {\n#include <fog_vertex>\n}",
      fragmentShader: "#include <common>\nvoid main() {\n#include <dithering_fragment>\n}"
    };
    material.onBeforeCompile(shader);
    return shader.fragmentShader;
  };
  const matte = applyPhotographicStudio(THREE, value, configuration({ groundFinish: "matte" }));
  assert.equal(matte.reflection, null, "no mirrored draw, no targets");
  assert.equal(Object.hasOwn(value.scene, "onBeforeRender"), false, "and nothing runs before a frame");
  assert.equal(matte.ground.material.roughness, PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES.matte.roughness);
  assert.doesNotMatch(floorShader(matte.ground.material), /uReflection/);

  const glossy = applyPhotographicStudio(THREE, value, configuration({ groundFinish: "glossy" }));
  const reflection = glossy.reflection;
  assert.ok(reflection);
  assert.equal(Object.hasOwn(value.scene, "onBeforeRender"), true, "drawn before each frame of the scene");
  assert.equal(glossy.ground.material.roughness, PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES.glossy.roughness);
  assert.match(floorShader(glossy.ground.material), /uReflection/);
  let released = 0;
  const dispose = reflection.dispose;
  reflection.dispose = () => { released += 1; dispose(); };
  applyPhotographicStudio(THREE, value, configuration({ groundFinish: "glossy" }));
  assert.equal(value.photographicStudio.reflection, reflection, "an unchanged finish keeps its reflection");

  // With the studio's lighting off a glossy floor reflects nothing, as it casts no shadow.
  const unlit = configuration({ groundFinish: "glossy" });
  unlit.lighting.enabled = false;
  applyPhotographicStudio(THREE, value, unlit);
  assert.equal(value.photographicStudio.reflection, null);
  assert.equal(released, 1);
  assert.equal(Object.hasOwn(value.scene, "onBeforeRender"), false);

  applyPhotographicStudio(THREE, value, configuration({ groundFinish: "glossy" }));
  assert.ok(value.photographicStudio.reflection);
  applyPhotographicStudio(THREE, value, configuration({ groundFinish: "matte" }));
  assert.equal(value.photographicStudio.reflection, null);
  assert.equal(Object.hasOwn(value.scene, "onBeforeRender"), false);
  assert.equal(value.photographicStudio.ground.material.roughness, PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES.matte.roughness);
  disposePhotographicStudio(value);
});

test("a software-rendered viewer gets no floor shadow, and a viewer's bake schedule reaches the one it gets", () => {
  const software = runtime();
  software.softwareRendering = true;
  const spared = applyPhotographicStudio(THREE, software, configuration());
  assert.equal(spared.keyLight.castShadow, false);
  assert.equal(spared.ground.material.isMeshStandardMaterial, true, "the floor itself stays");
  assert.equal(spared.contactShadow, null, "no probe depth pass and no bake passes");
  disposePhotographicStudio(software);

  // With an interval, a second key pass inside it composites and leaves the heights owed.
  const timers = [];
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration(), {
    contactShadow: {
      heightInterval: 100, now: () => 0, requestFrame: () => {},
      setTimer: (callback, ms) => timers.push(ms), clearTimer: () => {}
    }
  });
  const heights = [];
  const renderer = {
    autoClear: true,
    shadowMap: { enabled: true, autoUpdate: false, needsUpdate: false, render(lights) { heights.push(lights[0].name); } },
    getRenderTarget() { return null; }, setRenderTarget() {}, render() {}
  };
  const contact = state.contactShadow;
  const camera = new THREE.PerspectiveCamera();
  contact.layer.onBeforeRender(renderer, value.scene, camera);
  contact.sentinel.onBeforeShadow(renderer, contact.sentinel, camera, state.keyLight.shadow.camera);
  contact.layer.onBeforeRender(renderer, value.scene, camera);
  assert.deepEqual(heights, ["studio-contact-shadow-probe"]);
  assert.deepEqual(timers, [100]);
  disposePhotographicStudio(value);
});

test("background and floor updates retain the neutral owner's current reflection intensity", () => {
  const value = runtime();
  value.scene.environmentIntensity = 0;
  const recipe = configuration();
  recipe.lighting.enabled = false;
  try {
    applyPhotographicStudio(THREE, value, recipe);
    value.scene.environmentIntensity = 1;
    applyPhotographicStudio(THREE, value, recipe);
    assert.equal(value.photographicStudio.original.environmentIntensity, 0);
    assert.equal(value.scene.environmentIntensity, 1);
    assert.equal(value.photographicStudio.keyLight.visible, false);
    value.scene.environmentIntensity = 0.5;
    applyPhotographicStudio(THREE, value, recipe);
    assert.equal(value.scene.environmentIntensity, 0.5);
  } finally { disposePhotographicStudio(value); }
});

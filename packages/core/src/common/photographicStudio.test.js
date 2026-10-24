import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  applyPhotographicStudio,
  disposePhotographicStudio,
  sampleKey,
  softboxPoint
} from "./photographicStudio.js";
import {
  PHOTOGRAPHIC_STUDIO_BACKDROP,
  PHOTOGRAPHIC_STUDIO_FLOOR_FADE,
  PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES,
  PHOTOGRAPHIC_STUDIO_FRAME,
  PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT,
  PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY,
  PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX,
  PHOTOGRAPHIC_STUDIO_KEY_DIRECTION
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

test("only a near-black floor takes the neutral lift: a dark studio's floor keeps its own tone", () => {
  const emissive = groundColor => applyPhotographicStudio(THREE, runtime(), configuration({ groundColor })).ground.material.emissive.toArray();
  assert.deepEqual(emissive("#202226"), new THREE.Color("#202226").toArray(), "no grey haze over a dark backdrop");
  assert.deepEqual(emissive("#000000"), new THREE.Color("#000000").lerp(new THREE.Color(0xffffff), PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX).toArray(),
    "black takes the whole lift, so its shadow still shows");
});

test("photographic studio applies one scale-stable key, Neutral exposure, and origin-aligned backdrop", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ exposure: 2 }), {
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
  // A floor lighter than near-black keeps its own tone: no neutral lift.
  assert.deepEqual(state.ground.material.emissive.toArray(), new THREE.Color("#e7e7e5").toArray());
  assert.equal(
    state.ground.material.emissiveIntensity,
    PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY
  );
  assert.equal(state.ground.receiveShadow, false, "its shadow is the soft contact layer");
  assert.ok(state.contactShadow);
  assert.equal(state.ground.position.x, 10);
  assert.equal(state.ground.position.y, 10);
  assert.equal(state.ground.position.z, 0);
  // The plane ends where its fade does: `outer` times the model's reach (here its radius,
  // which is larger than its footprint's half-diagonal), fading from `inner` of it.
  const boundsRadius = Math.hypot(20, 30, 10);
  assert.equal(state.ground.scale.x, 2 * boundsRadius * PHOTOGRAPHIC_STUDIO_FLOOR_FADE.outer);
  assert.equal(state.ground.scale.y, state.ground.scale.x);
  assert.equal(state.floorFade.value, PHOTOGRAPHIC_STUDIO_FLOOR_FADE.inner / PHOTOGRAPHIC_STUDIO_FLOOR_FADE.outer);
  assert.equal(value.scene.environmentIntensity, 1);
  assert.equal(value.requestCount, 1);
});

test("floor defaults to the model's lowest point and can stand at the model origin (Z=0)", () => {
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
  const state = applyPhotographicStudio(THREE, value, configuration());
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
  // A colour lighter than near-black is its own emissive: no neutral lift.
  assert.ok(Math.abs(customEmissiveHsl.l - customColorHsl.l) < 1e-12);
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
  const state = applyPhotographicStudio(THREE, value, configuration({ color: "#202226" }));
  const shader = {
    uniforms: {},
    vertexShader: "#include <common>\nvoid main() {\n#include <fog_vertex>\n}",
    fragmentShader: "#include <common>\nvoid main() {\n#include <dithering_fragment>\n}"
  };
  state.ground.material.onBeforeCompile(shader);
  // The floor fades out before it is dithered, so its rim never shows (the fade's own test says how).
  assert.match(shader.fragmentShader, /gl_FragColor\.a \*= studioFloorFade\(\);/);
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
  const state = applyPhotographicStudio(THREE, snapshot, configuration({ color: "#202226" }), { ditherScale: 2 });
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
  assert.equal(state.backdrop.object.material.defines?.STUDIO_DITHER_SCALE, "2.0000", "and the backdrop's");
  // A viewer shows its pixels as drawn and passes no scale: nothing is defined, so its
  // programs, and its pixels, are the ones they always were; a scale back at 1 is that again.
  const viewer = runtime();
  const viewerState = applyPhotographicStudio(THREE, viewer, configuration({ color: "#202226" }));
  assert.equal(viewerState.ground.material.defines?.STUDIO_DITHER_SCALE, undefined);
  assert.equal(viewerState.contactShadow.layer.material.defines?.STUDIO_DITHER_SCALE, undefined);
  applyPhotographicStudio(THREE, snapshot, configuration({ color: "#202226" }), { ditherScale: 1 });
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
  // Its mirrored draw shows the model alone: not the floor, its shadow, nor the backdrop.
  for (const hidden of [glossy.ground, glossy.contactShadow.layer, glossy.backdrop.object]) {
    assert.ok(glossy.reflectionHidden().includes(hidden), hidden.name);
  }
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

test("the floor has no edge: it fades out from the model to its rim, with its reflection, whatever the camera sees", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ groundFinish: "glossy" }));
  const shader = {
    uniforms: {},
    vertexShader: "#include <common>\nvoid main() {\n#include <begin_vertex>\n#include <fog_vertex>\n}",
    fragmentShader: "#include <common>\nvoid main() {\n#include <dithering_fragment>\n}"
  };
  state.ground.material.onBeforeCompile(shader);
  // One uniform, the fade's start as a share of the plane's half-width, shared by every program.
  assert.equal(shader.uniforms.uStudioFloorFade, state.floorFade);
  assert.match(shader.vertexShader, /vStudioFloorPlane = position\.xy;/);
  // Out to its inscribed circle: no corner ever shows, and the square's corners are drawn clear.
  assert.match(shader.fragmentShader, /smoothstep\(uStudioFloorFade, 1\.0, length\(vStudioFloorPlane\) \* 2\.0\)/);
  // After the reflection is laid over it, so the reflection fades with the floor.
  assert.ok(shader.fragmentShader.indexOf("uReflectionReady > 0.5") < shader.fragmentShader.indexOf("studioFloorFade();"));
  // A flat, wide model reaches past its radius: its footprint sets the reach.
  const wide = { min: [-100, -5, 0], max: [100, 5, 2] };
  applyPhotographicStudio(THREE, value, configuration(), { bounds: wide, groundBounds: wide });
  assert.ok(state.ground.scale.x >= 2 * Math.hypot(200, 10) / 2 * PHOTOGRAPHIC_STUDIO_FLOOR_FADE.outer - 1e-9);
  disposePhotographicStudio(value);
});

test("the backdrop is a studio sweep in the background colour, never a flat fill, and is drawn behind everything", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration({ color: "#202226" }));
  const backdrop = state.backdrop.object;
  assert.equal(backdrop.parent, state.group);
  assert.equal(value.scene.background.getHexString(), "202226", "the clear under it is the colour, as before");
  const material = backdrop.material;
  assert.equal(material.depthWrite, false, "it writes no depth: the frame's occlusion never darkens it");
  assert.equal(material.depthTest, false);
  assert.equal(material.toneMapped, false);
  assert.equal(backdrop.castShadow, false);
  assert.equal(backdrop.frustumCulled, false);
  assert.ok(backdrop.renderOrder < state.ground.renderOrder, "first of everything");
  assert.equal(new THREE.Raycaster(new THREE.Vector3(0, 0, 5), new THREE.Vector3(0, 0, -1)).intersectObject(backdrop).length, 0, "never picked");
  // The colour in display values, as a clear writes it; a dark one shaded more than a light one.
  const [r, g, b] = material.uniforms.uColor.value.toArray();
  assert.deepEqual([r, g, b].map((channel) => Math.round(channel * 255)), [0x20, 0x22, 0x26]);
  const darkShade = material.uniforms.uShape.value.y;
  assert.equal(material.uniforms.uShape.value.x, PHOTOGRAPHIC_STUDIO_BACKDROP.lift);
  applyPhotographicStudio(THREE, value, configuration({ color: "#ffffff" }));
  assert.ok(Math.abs(material.uniforms.uShape.value.y - PHOTOGRAPHIC_STUDIO_BACKDROP.shade.light) < 1e-9);
  assert.ok(darkShade > material.uniforms.uShape.value.y);
  assert.equal(state.backdrop.object, backdrop, "updated in place");
  disposePhotographicStudio(value);
  assert.equal(backdrop.parent, null);
});

test("the backdrop carries the background's alpha, and draws nothing where the background is taken away", () => {
  const value = runtime();
  const recipe = configuration();
  recipe.backdrop.opacity = 0.35;
  const state = applyPhotographicStudio(THREE, value, recipe);
  const backdrop = state.backdrop.object;
  const uniforms = backdrop.material.uniforms;
  const camera = new THREE.PerspectiveCamera(40, 1.5, 1, 1000);
  camera.position.set(0, -100, 0);
  camera.up.set(0, 0, 1);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  let clearAlpha = 0.35;
  let target = null;
  const renderer = {
    getClearAlpha: () => clearAlpha,
    getRenderTarget: () => target,
    getContextAttributes: () => ({ premultipliedAlpha: true })
  };
  const draw = () => backdrop.onBeforeRender(renderer, value.scene, camera);
  assert.equal(backdrop.visible, true);
  draw();
  assert.equal(uniforms.uAlpha.value, 0.35, "half-transparent, it keeps its gradient");
  assert.equal(uniforms.uPremultiply.value, 1, "premultiplied, as three clears a premultiplied canvas");
  assert.equal(uniforms.uLinear.value, 0, "the canvas takes display colour");
  assert.ok(Math.abs(uniforms.uAspect.value - 1.5) < 1e-9);
  assert.deepEqual(uniforms.uCameraWorld.value.toArray(), camera.matrixWorld.toArray());
  // A thumbnail takes the background away and clears to nothing: so does the backdrop.
  clearAlpha = 0;
  draw();
  assert.equal(uniforms.uAlpha.value, 0);
  // Opaque, it is the background whatever the clear's alpha.
  applyPhotographicStudio(THREE, value, configuration());
  draw();
  assert.equal(uniforms.uAlpha.value, 1);
  // Into a target three does not draw as the canvas, in linear light.
  target = { isXRRenderTarget: false };
  draw();
  assert.equal(uniforms.uLinear.value, 1);
  target = { isXRRenderTarget: true };
  draw();
  assert.equal(uniforms.uLinear.value, 0);
  // Transparent, it would draw exactly the clear: it is not drawn at all, and alpha stays clean.
  applyPhotographicStudio(THREE, value, configuration({ transparent: true }));
  assert.equal(backdrop.visible, false);
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

test("the studio's lighting is drawn through its frame, more samples at Final, none in software or without the lighting", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration());
  assert.ok(state.frame, "a frame while the studio lights the model");
  assert.equal(state.frame.samples, PHOTOGRAPHIC_STUDIO_FRAME.samples.preview);
  applyPhotographicStudio(THREE, value, { ...configuration(), quality: "final" });
  assert.equal(state.frame.samples, PHOTOGRAPHIC_STUDIO_FRAME.samples.final);
  const frame = state.frame;
  applyPhotographicStudio(THREE, value, { ...configuration(), lighting: { ...configuration().lighting, enabled: false } });
  assert.equal(state.frame, null, "an unlit studio is one draw");
  assert.throws(() => frame.render(value.renderer, value.scene, new THREE.PerspectiveCamera()), /disposed/);
  applyPhotographicStudio(THREE, value, configuration(), { frame: false });
  assert.equal(state.frame, null, "a caller may draw it as one draw");

  const software = { ...runtime(), softwareRendering: true };
  assert.equal(applyPhotographicStudio(THREE, software, configuration()).frame, null);

  const disposed = runtime();
  const owned = applyPhotographicStudio(THREE, disposed, configuration()).frame;
  disposePhotographicStudio(disposed);
  assert.throws(() => owned.render(disposed.renderer, disposed.scene, new THREE.PerspectiveCamera()), /disposed/);
});

test("a still frame's samples move the key across its softbox, square to it and as wide as Size makes it, and back to rest", () => {
  const value = runtime();
  const state = applyPhotographicStudio(THREE, value, configuration());
  const rest = state.keyLight.position.clone();
  const direction = rest.clone().sub(state.target.position).normalize();
  assert.equal(sampleKey(state, 0), false, "the first sample is the key at rest");
  const offsets = [];
  for (let index = 1; index <= 16; index += 1) {
    assert.equal(sampleKey(state, index), true);
    const offset = state.keyLight.position.clone().sub(rest);
    assert.ok(Math.abs(offset.dot(direction)) < 1e-6 * rest.length(), "across the softbox's face");
    offsets.push(offset.length());
  }
  assert.equal(sampleKey(state, 16), false, "the same sample moves nothing");
  assert.equal(sampleKey(state, 0), true);
  assert.ok(state.keyLight.position.equals(rest));
  for (const point of [1, 2, 3, 40].map(softboxPoint)) for (const value of point) assert.ok(value >= -1 && value <= 1);

  // A larger softbox spreads the samples, so its shadows are softer.
  applyPhotographicStudio(THREE, value, configuration({ size: 2 }));
  const wider = state.keyLight.position.clone();
  sampleKey(state, 5);
  assert.ok(Math.abs(state.keyLight.position.distanceTo(wider) - 2 * offsets[4]) < 1e-6 * wider.length());
});

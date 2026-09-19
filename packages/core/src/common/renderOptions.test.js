import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  normalizeThemeSettings
} from "./themeSettings.js";
import {
  addFloor,
  applyLighting,
  createSharedRenderOptions,
  RENDER_SCENE_SCALE,
  boundsCorners,
  boundsFromVertices,
  centerAndRadiusFromBounds,
  fitOrthographicCamera,
  fitPerspectiveCamera,
  fitCameraDepthToBounds,
  frameHalfHeightForView,
  framePadding,
  inferRenderSceneScale,
  outputSize,
  rendererDataUrlWithOptionalLabel,
  resolveRenderView,
  snapshotUsesLogarithmicDepthBuffer
} from "./renderOptions.js";

const SCALE_SETTINGS = Object.freeze({
  [RENDER_SCENE_SCALE.CAD]: Object.freeze({
    minBoundsSpan: 1,
    minModelRadius: 1,
    minFloorSize: 100,
    minCameraDistance: 10,
    minCameraFar: 1000
  }),
  [RENDER_SCENE_SCALE.URDF]: Object.freeze({
    minBoundsSpan: 0.05,
    minModelRadius: 0.05,
    minFloorSize: 0.05,
    minCameraDistance: 0.5,
    minCameraFar: 10
  })
});

function assertClose(actual, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} !== ${expected}`);
}

function groundHitAtNdc(camera, x, y, groundZ) {
  camera.updateMatrixWorld(true);
  const cameraPosition = new THREE.Vector3();
  const origin = new THREE.Vector3();
  const direction = new THREE.Vector3();
  camera.getWorldPosition(cameraPosition);
  if (camera.isPerspectiveCamera) {
    origin.copy(cameraPosition);
    direction.set(x, y, 0).unproject(camera).sub(origin);
  } else {
    origin.set(x, y, -1).unproject(camera);
    direction.set(0, 0, -1).transformDirection(camera.matrixWorld);
  }
  if (Math.abs(direction.z) <= 1e-12) return null;
  const hit = origin.addScaledVector(direction, (groundZ - origin.z) / direction.z);
  const depth = -hit.clone().applyMatrix4(camera.matrixWorldInverse).z;
  return depth > 0 ? { hit, depth } : null;
}

test("shared render options preserve explicit caller-owned values without defaults", () => {
  const options = createSharedRenderOptions({
    displayMode: "wireframe",
    background: false,
    renderScale: 0
  });

  assert.equal(options.themeSettings, null);
  assert.equal(options.display, null);
  assert.equal(Object.hasOwn(options, "displayMode"), false);
  assert.equal(options.background, false);
  assert.equal(options.renderScale, 0);
});

test("render display snapshots use ordinary depth for studio shadows", () => {
  assert.equal(snapshotUsesLogarithmicDepthBuffer({}), true);
  assert.equal(snapshotUsesLogarithmicDepthBuffer({ display: { mode: "shaded" } }), true);
  assert.equal(snapshotUsesLogarithmicDepthBuffer({ display: { mode: "render" } }), false);
});

test("view presets and azimuth/elevation camera parsing remain stable", () => {
  const top = resolveRenderView("top");
  assert.equal(top.name, "top");
  assert.deepEqual(top.direction, [0, 0, 1]);
  assert.deepEqual(top.up, [0, 1, 0]);

  const custom = resolveRenderView("45:30");
  assert.equal(custom.name, "45:30");
  assertClose(custom.direction[0], Math.SQRT1_2 * Math.cos(Math.PI / 6));
  assertClose(custom.direction[1], -Math.SQRT1_2 * Math.cos(Math.PI / 6));
  assertClose(custom.direction[2], 0.5);
});

test("scene scale inference, bounds, and camera framing are policy-free helpers", () => {
  assert.equal(inferRenderSceneScale({ explicit: "urdf" }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ kind: "sdf" }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ parts: [{ linkName: "base_link" }] }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ kind: "glb", parts: [] }), RENDER_SCENE_SCALE.CAD);

  const bounds = boundsFromVertices(new Float32Array([0, 0, 0, 2, 4, 6]));
  assert.deepEqual(bounds, { min: [0, 0, 0], max: [2, 4, 6] });

  const { center, radius } = centerAndRadiusFromBounds(bounds, RENDER_SCENE_SCALE.CAD, SCALE_SETTINGS);
  assert.deepEqual(center.toArray(), [1, 2, 3]);
  assertClose(radius, Math.sqrt(56) / 2);

  const view = resolveRenderView("iso");
  const halfHeight = frameHalfHeightForView(view, bounds, 800, 600, 0.12, RENDER_SCENE_SCALE.CAD, SCALE_SETTINGS);
  assert.ok(halfHeight > 0);

  const camera = new THREE.OrthographicCamera();
  fitOrthographicCamera(camera, view, bounds, 800, 600, {
    padding: 0.12,
    sceneScale: RENDER_SCENE_SCALE.CAD,
    settingsByScale: SCALE_SETTINGS
  });
  assertClose(camera.top, halfHeight);
  assertClose(camera.bottom, -halfHeight);
  assertClose(camera.left, -halfHeight * (800 / 600));
  assertClose(camera.right, halfHeight * (800 / 600));
  assert.equal(camera.near, 0.01);
  assert.equal(camera.far >= 1000, true);
});

test("automatic perspective framing fits bounds to padding at wide and tall aspects", () => {
  const bounds = { min: [-50, -10, -5], max: [50, 10, 5] };
  const padding = 0.04;
  const safeContentScale = 1 - padding * 2;
  const fittedDistance = (width, height) => {
    const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 1000);
    const resolved = fitPerspectiveCamera(
      camera,
      { preset: "front", projection: "perspective" },
      bounds,
      width,
      height,
      {
        padding,
        sceneScale: RENDER_SCENE_SCALE.CAD,
        settingsByScale: SCALE_SETTINGS
      }
    );
    const projected = boundsCorners(bounds).map((point) => point.project(camera));
    const maxX = Math.max(...projected.map((point) => Math.abs(point.x)));
    const maxY = Math.max(...projected.map((point) => Math.abs(point.y)));
    assert.ok(maxX <= safeContentScale + 1e-6, `${maxX} exceeds horizontal padding`);
    assert.ok(maxY <= safeContentScale + 1e-6, `${maxY} exceeds vertical padding`);
    assert.ok(Math.max(maxX, maxY) >= safeContentScale - 1e-6, "fit should use the limiting output dimension");
    return new THREE.Vector3(...resolved.position).distanceTo(new THREE.Vector3(...resolved.target));
  };

  const wideDistance = fittedDistance(800, 400);
  const tallDistance = fittedDistance(400, 800);
  assert.ok(tallDistance > wideDistance, `${tallDistance} should exceed ${wideDistance}`);
});

test("tight perspective framing can fit visible points instead of empty bounds corners", () => {
  const bounds = { min: [-100, -100, -100], max: [100, 100, 100] };
  const fit = (framePoints = null) => {
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000);
    const resolved = fitPerspectiveCamera(
      camera,
      { preset: "front", projection: "perspective" },
      bounds,
      480,
      480,
      {
        framePoints,
        padding: 0.04,
        sceneScale: RENDER_SCENE_SCALE.CAD,
        settingsByScale: SCALE_SETTINGS
      }
    );
    return {
      camera,
      distance: new THREE.Vector3(...resolved.position).distanceTo(new THREE.Vector3(...resolved.target))
    };
  };
  const visiblePoints = [
    new THREE.Vector3(-100, 0, 0),
    new THREE.Vector3(100, 0, 0),
    new THREE.Vector3(0, -100, 0),
    new THREE.Vector3(0, 100, 0),
    new THREE.Vector3(0, 0, -100),
    new THREE.Vector3(0, 0, 100)
  ];
  const boundsFit = fit();
  const tightFit = fit(visiblePoints);

  assert.ok(tightFit.distance < boundsFit.distance, `${tightFit.distance} should be closer than ${boundsFit.distance}`);
  const maxProjected = Math.max(...visiblePoints.flatMap((point) => {
    const projected = point.clone().project(tightFit.camera);
    return [Math.abs(projected.x), Math.abs(projected.y)];
  }));
  assertClose(maxProjected, 0.92, 1e-6);
});

test("perspective framing preserves explicit camera position and target", () => {
  const cameraSpec = {
    position: [23, -41, 17],
    target: [1, 2, 3],
    up: [0, 0, 1],
    projection: "perspective"
  };
  const bounds = { min: [-500, -200, -100], max: [600, 300, 200] };
  for (const [width, height, padding] of [[1600, 400, 0], [400, 1600, 0.15]]) {
    const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 1000);
    const resolved = fitPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
      framePoints: [new THREE.Vector3(1000, 1000, 1000)],
      padding,
      sceneScale: RENDER_SCENE_SCALE.CAD,
      settingsByScale: SCALE_SETTINGS
    });
    assert.deepEqual(camera.position.toArray(), cameraSpec.position);
    assert.deepEqual(resolved.position, cameraSpec.position);
    assert.deepEqual(resolved.target, cameraSpec.target);
  }
});

test("lens focal length changes perspective while automatic framing keeps the subject in frame", () => {
  const bounds = { min: [-20, -15, 0], max: [20, 15, 25] };
  for (const [width, height] of [[1200, 800], [800, 1200]]) {
    const distances = [];
    for (const focalLength of [24, 85, 200]) {
      const camera = new THREE.PerspectiveCamera(48);
      const spec = { preset: "iso", projection: "perspective", focalLength };
      const result = fitPerspectiveCamera(camera, spec, bounds, width, height, {
        padding: 0.04, sceneScale: RENDER_SCENE_SCALE.CAD, settingsByScale: SCALE_SETTINGS
      });
      assertClose(camera.getFocalLength(), focalLength);
      assert.equal(result.focalLength, focalLength);
      for (const x of [-20, 20]) for (const y of [-15, 15]) for (const z of [0, 25]) {
        const point = new THREE.Vector3(x, y, z).project(camera);
        assert.ok(Math.abs(point.x) <= 0.920001 && Math.abs(point.y) <= 0.920001);
      }
      distances.push(camera.position.distanceTo(new THREE.Vector3(...result.target)));
    }
    assert.ok(distances[0] < distances[1] && distances[1] < distances[2]);
  }
});

test("photographic depth fitting preserves the subject at CAD and robot scales as cameras move", () => {
  for (const scale of [0.001, 1, 1000]) {
    const bounds = { min: [-20 * scale, -10 * scale, 0], max: [20 * scale, 10 * scale, 8 * scale] };
    const camera = new THREE.PerspectiveCamera(40, 1, 0.00001, 50000);
    for (const position of [[60, -60, 80], [90, 20, 15], [300, 300, 300]]) {
      camera.position.set(...position.map((value) => value * scale));
      camera.lookAt(0, 0, 4 * scale);
      assert.equal(fitCameraDepthToBounds(camera, bounds), true);
      assert.ok(camera.far / camera.near < 100, "ordinary depth stays precise around the subject and studio stage");
      for (const point of boundsCorners(bounds)) {
        const z = point.project(camera).z;
        assert.ok(z > -1 && z < 1, `subject is not clipped: ${z}`);
      }
      assert.equal(fitCameraDepthToBounds(camera, bounds), false, "unchanged cameras do not rewrite projection");
    }
    camera.position.set(0, 0, 4 * scale);
    camera.lookAt(0, 1, 4 * scale);
    fitCameraDepthToBounds(camera, bounds);
    assert.ok(camera.near > 0 && camera.far > camera.near, "camera inside the subject remains navigable");
  }
});

test("macro views fit visible occurrences without collapsing depth inside an assembly box", () => {
  for (const scale of [0.001, 1, 1000]) {
    const bounds = { min: [-100 * scale, -100 * scale, 0], max: [100 * scale, 100 * scale, 20 * scale] };
    const camera = new THREE.PerspectiveCamera(40, 1, 0.01 * scale, 10000 * scale);
    camera.position.set(0, -20 * scale, 15 * scale); camera.lookAt(0, 0, 10 * scale);
    const partBounds = { min: [-2 * scale, -2 * scale, 9 * scale], max: [2 * scale, 2 * scale, 11 * scale] };
    const records = [{ partBounds }, { partBounds, effectMatrix: new THREE.Matrix4().makeTranslation(100 * scale, -20 * scale, 0) }];
    fitCameraDepthToBounds(camera, bounds);
    const aggregateNear = camera.near;
    fitCameraDepthToBounds(camera, bounds, { displayRecords: records });
    assert.ok(camera.near > aggregateNear * 1000, "offscreen assembly extents cannot destroy closeup precision");
    for (const point of boundsCorners(partBounds)) {
      const projected = point.project(camera);
      assert.ok(projected.z > -1 && projected.z < 1, "visible part is retained");
    }
    records[0].effectMatrix = new THREE.Matrix4().makeTranslation(0, -10 * scale, 0);
    const previousNear = camera.near;
    fitCameraDepthToBounds(camera, bounds, { displayRecords: records });
    assert.ok(camera.near < previousNear, "animated occurrences update the depth fit");
    for (const point of boundsCorners(partBounds)) {
      const projected = point.applyMatrix4(records[0].effectMatrix).project(camera);
      assert.ok(projected.z > -1 && projected.z < 1);
    }
    records[0].tubeGpuState = { active: true };
    fitCameraDepthToBounds(camera, bounds, { displayRecords: records });
    assertClose(camera.near, aggregateNear, 1e-8 * scale);
  }
});

test("photographic depth fitting retains foreground ground at oblique and low camera angles", () => {
  for (const scale of [0.001, 1, 1000]) {
    const bounds = { min: [-20 * scale, -10 * scale, 0], max: [20 * scale, 10 * scale, 8 * scale] };
    const radius = Math.hypot(40 * scale, 20 * scale, 8 * scale) / 2;
    const cases = [
      {
        camera: new THREE.PerspectiveCamera(50, 16 / 9, 0.000001 * scale, 100000 * scale),
        position: [0, -55, 6]
      },
      {
        camera: new THREE.OrthographicCamera(-30 * scale, 30 * scale, 18 * scale, -18 * scale, 0.000001 * scale, 100000 * scale),
        position: [40, -40, 40]
      }
    ];
    for (const { camera, position } of cases) {
      camera.position.set(...position.map((value) => value * scale));
      camera.lookAt(0, 0, 4 * scale);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      const hits = [[-1, -1], [1, -1], [-1, 1], [1, 1]]
        .map(([x, y]) => groundHitAtNdc(camera, x, y, bounds.min[2]))
        .filter(Boolean);
      const foreground = hits.reduce((nearest, entry) => (
        !nearest || entry.depth < nearest.depth ? entry : nearest
      ), null);
      assert.ok(foreground, "the fixture exposes foreground ground");

      const subjectNear = Math.min(...boundsCorners(bounds).map(
        (point) => -point.applyMatrix4(camera.matrixWorldInverse).z
      )) - radius * 0.1;
      assert.ok(subjectNear > foreground.depth, "the old subject-only near plane would clip the ground");

      fitCameraDepthToBounds(camera, bounds);
      const projected = foreground.hit.clone().project(camera);
      assert.ok(projected.z > -1 && projected.z < 1, `foreground ground is not clipped: ${projected.z}`);
      assert.ok(camera.near > radius * 0.01, "near stays view-fitted instead of collapsing to the safety floor");
    }
  }
});

test("orthographic framing restores canonical half-height and zoom", () => {
  const camera = new THREE.OrthographicCamera();
  const resolved = fitOrthographicCamera(
    camera,
    {
      preset: "front",
      projection: "orthographic",
      orthographicHalfHeight: 42,
      zoom: 1.5
    },
    { min: [-500, -500, -500], max: [500, 500, 500] },
    800,
    400,
    {
      padding: 0.04,
      sceneScale: RENDER_SCENE_SCALE.CAD,
      settingsByScale: SCALE_SETTINGS
    }
  );

  assert.equal(resolved.orthographicHalfHeight, 42);
  assert.equal(camera.top, 42);
  assert.equal(camera.bottom, -42);
  assert.equal(camera.left, -84);
  assert.equal(camera.right, 84);
  assert.equal(camera.zoom, 1.5);
});

test("output sizing and padding helpers preserve snapshot fallback semantics", () => {
  assert.deepEqual(outputSize({}, {}), { width: 1400, height: 900 });
  assert.deepEqual(outputSize({ width: 320, height: 240 }, { output: { width: 1400, height: 900 } }), { width: 320, height: 240 });
  assert.deepEqual(outputSize({}, { output: { width: 1600, height: 1200 } }), { width: 1600, height: 1200 });
  assert.equal(framePadding({}), 0.04);
  assert.equal(framePadding({ output: { padding: 0 } }), 0);
  assert.equal(framePadding({ output: { padding: 0.02 } }), 0.02);
  assert.equal(framePadding({ output: { padding: -0.02 } }), 0);
  assert.equal(framePadding({ output: { paddingPercent: 0.25 } }), 0.15);
  assert.equal(framePadding({ output: { paddingPercent: 0.13 } }), 0.13);
});

test("supersampled PNG capture resamples the complete drawing buffer to the requested output pixels", (t) => {
  const originalDocument = globalThis.document;
  const calls = [];
  let exportedCanvas = null;
  globalThis.document = {
    createElement(tag) {
      assert.equal(tag, "canvas");
      const context = {
        imageSmoothingEnabled: false,
        imageSmoothingQuality: "low",
        drawImage(...args) {
          calls.push(args);
        }
      };
      exportedCanvas = {
        width: 0,
        height: 0,
        getContext(kind) {
          assert.equal(kind, "2d");
          return context;
        },
        toDataURL(type) {
          assert.equal(type, "image/png");
          return "data:image/png;base64,resampled";
        }
      };
      return exportedCanvas;
    }
  };
  t.after(() => {
    if (originalDocument === undefined) {
      delete globalThis.document;
    } else {
      globalThis.document = originalDocument;
    }
  });

  const source = {
    width: 2400,
    height: 1800,
    toDataURL() {
      throw new Error("supersampled buffer must not be exported directly");
    }
  };
  const result = rendererDataUrlWithOptionalLabel({ domElement: source }, "", {}, {
    width: 1200,
    height: 900
  });

  assert.equal(result, "data:image/png;base64,resampled");
  assert.equal(exportedCanvas.width, 1200);
  assert.equal(exportedCanvas.height, 900);
  assert.equal(exportedCanvas.getContext("2d").imageSmoothingEnabled, true);
  assert.equal(exportedCanvas.getContext("2d").imageSmoothingQuality, "high");
  assert.deepEqual(calls, [[source, 0, 0, 2400, 1800, 0, 0, 1200, 900]],
    "the full supersampled frame must cover the full requested output, without crop");
});

test("inspection grid uses fixed ink and shared Viewer spacing", () => {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    { min: [0, 0, 0], max: [10, 10, 10] },
    normalizeThemeSettings({
      floor: { mode: "none", enabled: false }
    }),
    RENDER_SCENE_SCALE.CAD,
    SCALE_SETTINGS,
    { grid: { enabled: true, centerColor: "#123456", cellColor: "#abcdef", opacity: 0.37, density: 2 } }
  );

  const grid = scene.children[0];
  const materials = Array.isArray(grid.material) ? grid.material : [grid.material];
  assert.equal(grid.type, "GridHelper");
  assert.equal(grid.geometry.getAttribute("position").count, 4 * (28 + 1));
  assert.equal(materials[0].opacity, 0.16);
  assert.equal(materials[0].transparent, true);
  assert.equal(materials[0].depthWrite, false);
});

test("display guides render independently from the studio stage floor", () => {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    { min: [0, 0, 0], max: [10, 10, 10] },
    normalizeThemeSettings({
      floor: {
        mode: "stage",
        enabled: true,
        color: "#ddeeff",
        roughness: 0.36,
        reflectivity: 0.42,
        shadowOpacity: 0.25
      }
    }),
    RENDER_SCENE_SCALE.CAD,
    SCALE_SETTINGS,
    { grid: { enabled: true, centerColor: "#123456", cellColor: "#abcdef", opacity: 0.37, density: 2 } }
  );

  const grid = scene.children.find((child) => child.type === "GridHelper");
  const plane = scene.children.find((child) => child.material?.isMeshPhysicalMaterial);
  const shadow = scene.children.find((child) => child.material?.isShadowMaterial);
  const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];

  assert.ok(grid);
  assert.ok(plane);
  assert.ok(shadow);
  assert.equal(gridMaterials[0].opacity, 0.16);
  assert.equal(grid.position.z, 0);
  assert.equal(plane.material.color.getHexString(), "ddeeff");
  assert.equal(plane.material.roughness, 0.36);
  assert.ok(Math.abs(plane.material.reflectivity - 0.42) < 1e-9);
  assert.equal(plane.material.specularIntensity, 1);
  assert.equal(plane.material.metalness, 0);
  assert.equal(shadow.receiveShadow, true);
  assert.equal(shadow.material.opacity, 0.25);
});

test("snapshot lights scale to model bounds and fit the directional shadow camera", () => {
  const scene = new THREE.Scene();
  const lights = applyLighting(scene, normalizeThemeSettings({
    lighting: {
      directional: { position: { x: 240, y: -150, z: 340 } },
      spot: { enabled: true, distance: 600, position: { x: 160, y: -120, z: 140 } }
    }
  }), {
    bounds: { min: [0, 0, 0], max: [760, 0, 0] },
    sceneScale: RENDER_SCENE_SCALE.CAD,
    shadowMapSize: 512
  });

  assert.equal(lights.radius, 380);
  assert.equal(lights.positionScale, 0.5);
  assert.deepEqual(lights.directional.position.toArray(), [120, -75, 170]);
  assert.equal(lights.spot.distance, 300);
  assert.equal(lights.directional.shadow.mapSize.x, 512);
  assert.equal(lights.directional.shadow.camera.left, -1064);
  assert.equal(lights.directional.shadow.camera.right, 1064);
  assert.ok(lights.directional.shadow.camera.far >= lights.directional.position.length());
});

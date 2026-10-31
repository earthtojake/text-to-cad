import assert from "node:assert/strict";
import test from "node:test";

import {
  PROCEDURAL_STUDIO_ENVIRONMENT_ID,
  createEnvironmentResource,
  createStudioEnvironmentScene,
  disposeEnvironmentResource,
  environmentResourceIdentity
} from "./environmentMap.js";
import {
  PHOTOGRAPHIC_STUDIO_BOUNCE_DIRECTION,
  PHOTOGRAPHIC_STUDIO_FILL_DIRECTION,
  PHOTOGRAPHIC_STUDIO_KEY_DIRECTION,
  PHOTOGRAPHIC_STUDIO_PANELS,
  PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE
} from "./photographicStudioRig.js";

test("environment identity follows physical card controls but not studio rotation or backdrop", () => {
  const base = {
    studio: "light",
    lighting: { rotation: 0, size: 1, fill: 0.25 },
    backdrop: { color: "#ffffff" }
  };
  assert.equal(PROCEDURAL_STUDIO_ENVIRONMENT_ID, "photographic-softbox");
  assert.equal(
    environmentResourceIdentity(base, { size: 512 }),
    "photographic-softbox:[1,0.25,512]"
  );
  assert.equal(
    environmentResourceIdentity({
      ...base,
      studio: "dark",
      lighting: { ...base.lighting, rotation: 135 },
      backdrop: { color: "#101010", transparent: true }
    }, { size: 512 }),
    environmentResourceIdentity(base, { size: 512 })
  );
  assert.notEqual(
    environmentResourceIdentity({ ...base, lighting: { ...base.lighting, size: 2 } }, { size: 512 }),
    environmentResourceIdentity(base, { size: 512 })
  );
  assert.notEqual(
    environmentResourceIdentity({ ...base, lighting: { ...base.lighting, fill: 0.5 } }, { size: 512 }),
    environmentResourceIdentity(base, { size: 512 })
  );
});

test("procedural scene uses neutral HDR key and proportional fill cards", () => {
  const scene = createStudioEnvironmentScene({ lighting: { size: 2, fill: 0.25 } });
  const key = scene.getObjectByName("studio-key-card");
  const fill = scene.getObjectByName("studio-fill-card");
  const bounce = scene.getObjectByName("studio-bounce-card");

  assert.ok(key);
  assert.ok(fill);
  assert.ok(bounce);
  assert.equal(key.geometry.parameters.width, 5);
  assert.equal(key.geometry.parameters.height, 7.2);
  assert.equal(fill.geometry.parameters.width, 6.4);
  assert.equal(fill.geometry.parameters.height, 8.4);
  assert.equal(bounce.geometry.parameters.width, 8);
  assert.equal(bounce.geometry.parameters.height, 10);
  assert.equal(key.material.toneMapped, false);
  assert.ok(key.material.color.r > 1);
  // Fill sets both fill cards: the rear card and the bounce on the key's far side.
  assert.equal(fill.material.color.r / key.material.color.r, 0.25);
  assert.equal(bounce.material.color.r, fill.material.color.r);
  assert.equal(key.material.color.r, key.material.color.g);
  assert.equal(key.material.color.g, key.material.color.b);
  for (const [card, direction] of [
    [key, PHOTOGRAPHIC_STUDIO_KEY_DIRECTION],
    [fill, PHOTOGRAPHIC_STUDIO_FILL_DIRECTION],
    [bounce, PHOTOGRAPHIC_STUDIO_BOUNCE_DIRECTION]
  ]) {
    assert.ok(card.position.clone().normalize().distanceTo(
      new card.position.constructor(...direction).normalize()
    ) < 1e-12);
  }

  scene.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
});

test("zero fill removes both fill cards without changing the key", () => {
  const scene = createStudioEnvironmentScene({ lighting: { size: 1, fill: 0 } });
  assert.ok(scene.getObjectByName("studio-key-card"));
  assert.equal(scene.getObjectByName("studio-fill-card"), undefined);
  assert.equal(scene.getObjectByName("studio-bounce-card"), undefined);
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
});

test("the sources hang in a sweep, not a void: darkest at the horizon, dim overhead, a light floor below", () => {
  const scene = createStudioEnvironmentScene({});
  const room = scene.getObjectByName("studio-room");
  const position = room.geometry.getAttribute("position");
  const color = room.geometry.getAttribute("color");
  let top = 0, bottom = 0, darkest = 0;
  for (let index = 0; index < position.count; index += 1) {
    assert.equal(color.getX(index), color.getY(index));
    assert.equal(color.getY(index), color.getZ(index));
    if (position.getZ(index) > position.getZ(top)) top = index;
    if (position.getZ(index) < position.getZ(bottom)) bottom = index;
    if (color.getX(index) < color.getX(darkest)) darkest = index;
  }
  const { zenith, horizon, nadir } = PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE;
  assert.ok(Math.abs(color.getX(top) - zenith) < 1e-6);
  assert.ok(Math.abs(color.getX(bottom) - nadir) < 1e-6);
  assert.ok(Math.abs(color.getX(darkest) - horizon) < 1e-6);
  assert.ok(Math.abs(position.getZ(darkest)) < 1e-6, "the darkest band is the horizon");
  assert.ok(horizon > 0 && horizon < zenith && zenith < nadir);
  assert.equal(room.material.toneMapped, false);
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
});

test("the studio's soft sources are lit gradients: bright cores falling to their edges, strips standing upright", () => {
  const scene = createStudioEnvironmentScene({ lighting: { size: 1, fill: 0.25 } });
  for (const panel of PHOTOGRAPHIC_STUDIO_PANELS) {
    const mesh = scene.getObjectByName(panel.name);
    assert.ok(mesh, panel.name);
    assert.ok(mesh.position.clone().normalize().distanceTo(
      new mesh.position.constructor(...panel.direction).normalize()
    ) < 1e-12);
    const position = mesh.geometry.getAttribute("position");
    const color = mesh.geometry.getAttribute("color");
    let core = 0, corner = 0;
    for (let index = 0; index < position.count; index += 1) {
      const r = Math.hypot(position.getX(index) / panel.width, position.getY(index) / panel.height);
      if (r < Math.hypot(position.getX(core) / panel.width, position.getY(core) / panel.height)) core = index;
      if (r > Math.hypot(position.getX(corner) / panel.width, position.getY(corner) / panel.height)) corner = index;
    }
    assert.equal(color.getX(core), 1, "full radiance at the core");
    assert.ok(color.getX(corner) < 0.5, "falls well off toward the edges");
    assert.equal(mesh.material.color.r, panel.radiance);
    if (panel.up) {
      // The strip's height runs along its `up`.
      const along = new mesh.position.constructor(0, 1, 0).applyQuaternion(mesh.quaternion);
      assert.ok(along.distanceTo(new mesh.position.constructor(...panel.up).normalize()) < 0.1);
    }
  }
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
});

test("softbox size preserves every source's total flux while changing highlight area", () => {
  const small = createStudioEnvironmentScene({ lighting: { size: 0.5, fill: 0.25 } });
  const large = createStudioEnvironmentScene({ lighting: { size: 2, fill: 0.25 } });
  const flux = (scene, name) => {
    const mesh = scene.getObjectByName(name);
    return mesh.material.color.r * mesh.geometry.parameters.width * mesh.geometry.parameters.height;
  };
  for (const name of ["studio-key-card", "studio-fill-card", "studio-bounce-card", ...PHOTOGRAPHIC_STUDIO_PANELS.map((panel) => panel.name)]) {
    assert.ok(Math.abs(flux(small, name) - flux(large, name)) < 1e-9, name);
    assert.equal(large.getObjectByName(name).geometry.parameters.width, small.getObjectByName(name).geometry.parameters.width * 4);
  }
  for (const scene of [small, large]) {
    scene.traverse((object) => {
      object.geometry?.dispose?.();
      object.material?.dispose?.();
    });
  }
});

test("procedural environments require their owning WebGL renderer", () => {
  assert.throws(
    () => createEnvironmentResource(null, { lighting: { size: 1, fill: 0.25 } }),
    /WebGL renderer is required/
  );
});

test("environment disposal remains caller-owned", () => {
  let count = 0;
  const resource = { dispose() { count += 1; } };
  disposeEnvironmentResource(resource);
  assert.equal(count, 1);
  disposeEnvironmentResource(null);
});

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
  PHOTOGRAPHIC_STUDIO_FILL_DIRECTION,
  PHOTOGRAPHIC_STUDIO_KEY_DIRECTION
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

  assert.ok(key);
  assert.ok(fill);
  assert.equal(key.geometry.parameters.width, 5);
  assert.equal(key.geometry.parameters.height, 7.2);
  assert.equal(fill.geometry.parameters.width, 6.4);
  assert.equal(fill.geometry.parameters.height, 8.4);
  assert.equal(key.material.toneMapped, false);
  assert.ok(key.material.color.r > 1);
  assert.equal(fill.material.color.r / key.material.color.r, 0.25);
  assert.equal(key.material.color.r, key.material.color.g);
  assert.equal(key.material.color.g, key.material.color.b);
  assert.ok(key.position.clone().normalize().distanceTo(
    new key.position.constructor(...PHOTOGRAPHIC_STUDIO_KEY_DIRECTION).normalize()
  ) < 1e-12);
  assert.ok(fill.position.clone().normalize().distanceTo(
    new fill.position.constructor(...PHOTOGRAPHIC_STUDIO_FILL_DIRECTION).normalize()
  ) < 1e-12);

  scene.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
});

test("zero fill removes the fill card without changing the key", () => {
  const scene = createStudioEnvironmentScene({ lighting: { size: 1, fill: 0 } });
  assert.ok(scene.getObjectByName("studio-key-card"));
  assert.equal(scene.getObjectByName("studio-fill-card"), undefined);
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
});

test("softbox size preserves total card flux while changing highlight area", () => {
  const small = createStudioEnvironmentScene({ lighting: { size: 0.5, fill: 0.25 } });
  const large = createStudioEnvironmentScene({ lighting: { size: 2, fill: 0.25 } });
  const smallKey = small.getObjectByName("studio-key-card");
  const largeKey = large.getObjectByName("studio-key-card");
  const smallFlux = smallKey.material.color.r
    * smallKey.geometry.parameters.width
    * smallKey.geometry.parameters.height;
  const largeFlux = largeKey.material.color.r
    * largeKey.geometry.parameters.width
    * largeKey.geometry.parameters.height;
  assert.ok(Math.abs(smallFlux - largeFlux) < 1e-10);
  for (const scene of [small, large]) {
    scene.traverse((object) => {
      object.geometry?.dispose?.();
      object.material?.dispose?.();
    });
  }
});

test("procedural environments require their owning WebGL renderer", async () => {
  await assert.rejects(
    createEnvironmentResource(null, { lighting: { size: 1, fill: 0.25 } }),
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

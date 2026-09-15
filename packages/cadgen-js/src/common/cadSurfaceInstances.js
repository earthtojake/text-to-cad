function hasEmission(material) {
  const color = material?.emissive;
  return Number(material?.emissiveIntensity) > 0 && !!color && (color.r !== 0 || color.g !== 0 || color.b !== 0);
}

const materialPassKeys = new WeakMap();
const materialSyncKeys = new WeakMap();
const recordPassKeys = new WeakMap();
const arrayMap = Array.prototype.map;

function scalarKeyValue(value) {
  const type = typeof value;
  return value === null || type === "undefined" || type === "number" || type === "string" || type === "boolean";
}

function materialPassKey(material) {
  // Observe the values every time: author effects can mutate a material or its
  // emissive colour in place. Only the immutable serialized recipe is reused.
  const type = material?.type || "";
  const vertexColors = material?.vertexColors === true;
  const roughness = Number(material?.roughness);
  const metalness = Number(material?.metalness);
  const clearcoat = Number(material?.clearcoat);
  const clearcoatRoughness = Number(material?.clearcoatRoughness);
  const emissiveIntensity = Number(material?.emissiveIntensity) || 0;
  const emissionEnabled = hasEmission(material);
  const envMapIntensity = Number(material?.envMapIntensity) || 0;
  const side = material?.side;
  const depthTest = material?.depthTest !== false;
  const depthWrite = material?.depthWrite !== false;
  const polygonOffset = material?.polygonOffset === true;
  const polygonOffsetFactor = Number(material?.polygonOffsetFactor) || 0;
  const polygonOffsetUnits = Number(material?.polygonOffsetUnits) || 0;
  const cacheable = material && typeof material === "object" && scalarKeyValue(type) && scalarKeyValue(side);
  const previous = cacheable ? materialPassKeys.get(material) : null;
  if (previous && previous.type === type && previous.vertexColors === vertexColors
    && Object.is(previous.roughness, roughness) && Object.is(previous.metalness, metalness)
    && Object.is(previous.clearcoat, clearcoat) && Object.is(previous.clearcoatRoughness, clearcoatRoughness)
    && Object.is(previous.emissiveIntensity, emissiveIntensity) && previous.emissionEnabled === emissionEnabled
    && Object.is(previous.envMapIntensity, envMapIntensity) && Object.is(previous.side, side)
    && previous.depthTest === depthTest && previous.depthWrite === depthWrite
    && previous.polygonOffset === polygonOffset && Object.is(previous.polygonOffsetFactor, polygonOffsetFactor)
    && Object.is(previous.polygonOffsetUnits, polygonOffsetUnits)) return previous.key;
  const values = {
    type, vertexColors, roughness, metalness, clearcoat, clearcoatRoughness,
    emissiveIntensity, emissionEnabled, envMapIntensity, side, depthTest,
    depthWrite, polygonOffset, polygonOffsetFactor, polygonOffsetUnits,
  };
  const key = JSON.stringify(values);
  if (cacheable) materialPassKeys.set(material, { ...values, key });
  return key;
}

function recordPassKey(record) {
  const pass = materialPassKey(record?.material);
  const order = Number(record?.mesh?.renderOrder) || 0;
  const previous = recordPassKeys.get(record);
  if (previous?.pass === pass && Object.is(previous.order, order)) return previous.key;
  const key = `${pass}#order=${order}`;
  recordPassKeys.set(record, { pass, order, key });
  return key;
}

function instancingCandidate(record) {
  const matrix = record?.mesh?.matrix;
  return Boolean(
    record?.geometry &&
    record?.mesh &&
    record.mesh.visible !== false &&
    record?.material &&
    record.material.transparent !== true &&
    Number(record.material.opacity) >= 0.999 &&
    // The shared shader derives emission from instance diffuse colour. A
    // distinct emissive channel, including a uniform glow over vertex colours,
    // keeps its exact ordinary material instead of tinting it accidentally.
    (!hasEmission(record.material) || (
      !record.material.vertexColors && record.material.emissive.equals(record.material.color)
    )) &&
    record.effectVisible !== false &&
    !record.tubeDeformationState &&
    matrix?.determinant?.() >= 0
  );
}

export function surfaceInstancingStateEligible(settings = {}) {
  return !["transparent", "wireframe"].includes(String(settings.displayMode || "").trim()) &&
    Number(settings.materialSettings?.opacity ?? 1) >= 0.999;
}

function configureInstanceMaterial(material) {
  material.visible = true;
  material.color?.set?.(0xffffff);
  // Instance colour carries the occurrence's authored/fill colour through
  // both diffuse and the viewer's subtle base emissive response.
  if (hasEmission(material)) {
    material.emissive.set(0xffffff);
  }
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <emissivemap_fragment>",
      "#include <emissivemap_fragment>\n#ifdef USE_COLOR\ntotalEmissiveRadiance *= vColor.rgb;\n#endif"
    );
  };
  material.customProgramCacheKey = () => "cad-surface-instance-emissive-v1";
}

function materialSyncKey(material) {
  const pass = materialPassKey(material);
  const opacity = Number(material?.opacity);
  const alphaTest = Number(material?.alphaTest);
  const blending = material?.blending;
  const toneMapped = material?.toneMapped !== false;
  const clipIntersection = material?.clipIntersection === true;
  const clipShadows = material?.clipShadows === true;
  const planes = material?.clippingPlanes;
  const map = planes ? planes.map : Array.prototype.map;
  // A custom mapper may define behaviour beyond plane values. Preserve its
  // construction instead of treating it as an ordinary recipe.
  let cacheable = material && typeof material === "object" && scalarKeyValue(blending)
    && map === arrayMap && (!planes || Array.isArray(planes));
  const planeCount = cacheable && planes ? planes.length : 0;
  if (!cacheable) return JSON.stringify({
    pass, opacity, alphaTest, blending, toneMapped, clipIntersection, clipShadows,
    clippingPlanes: map.call(planes || [], (plane) => [
      Number(plane?.normal?.x) || 0,
      Number(plane?.normal?.y) || 0,
      Number(plane?.normal?.z) || 0,
      Number(plane?.constant) || 0,
    ]),
  });
  const previous = materialSyncKeys.get(material);
  let matches = previous && previous.pass === pass && Object.is(previous.opacity, opacity)
    && Object.is(previous.alphaTest, alphaTest) && Object.is(previous.blending, blending)
    && previous.toneMapped === toneMapped && previous.clipIntersection === clipIntersection
    && previous.clipShadows === clipShadows && previous.planeValues.length === planeCount * 4;
  let planeValues = matches ? null : new Array(planeCount * 4);
  for (let i = 0; i < planeCount; i += 1) {
    const offset = i * 4;
    // Match Array.map's per-index presence check. A getter for an earlier
    // plane can remove a later entry during this same traversal; that row
    // remains a hole, not a zero plane. Keep sparse recipes uncached.
    if (!(i in planes)) {
      if (matches) {
        matches = false;
        planeValues = previous.planeValues.slice(0, offset);
        planeValues.length = planeCount * 4;
      }
      planeValues[offset] = undefined;
      cacheable = false;
      continue;
    }
    const plane = planes[i];
    const x = Number(plane?.normal?.x) || 0;
    const y = Number(plane?.normal?.y) || 0;
    const z = Number(plane?.normal?.z) || 0;
    const constant = Number(plane?.constant) || 0;
    if (matches && (!Object.is(previous.planeValues[offset], x)
      || !Object.is(previous.planeValues[offset + 1], y)
      || !Object.is(previous.planeValues[offset + 2], z)
      || !Object.is(previous.planeValues[offset + 3], constant))) {
      matches = false;
      planeValues = previous.planeValues.slice(0, offset);
      planeValues.length = planeCount * 4;
    }
    if (!matches) {
      planeValues[offset] = x;
      planeValues[offset + 1] = y;
      planeValues[offset + 2] = z;
      planeValues[offset + 3] = constant;
    }
  }
  if (matches) return previous.key;
  const clippingPlanes = new Array(planeCount);
  for (let i = 0; i < planeValues.length; i += 4) {
    if (planeValues[i] !== undefined) clippingPlanes[i / 4] = planeValues.slice(i, i + 4);
  }
  const key = JSON.stringify({
    pass, opacity, alphaTest, blending, toneMapped, clipIntersection, clipShadows, clippingPlanes,
  });
  if (cacheable) materialSyncKeys.set(material, {
    pass, opacity, alphaTest, blending, toneMapped, clipIntersection, clipShadows, planeValues, key,
  });
  return key;
}

function float32Changed(values, offset, source, count) {
  for (let index = 0; index < count; index += 1) {
    if (values[offset + index] !== Math.fround(source[index])) return true;
  }
  return false;
}

// Collapse compatible occurrence meshes into one draw. Records retain their
// private Mesh as a transform/picking metadata proxy. Its material is hidden,
// so it issues no draw, while remaining in the scene graph for world-matrix
// updates and the viewer's existing per-record raycast path.
export function buildCadSurfaceInstanceSets(THREE, records, modelGroup) {
  const byGeometry = new Map();
  for (const record of records || []) {
    if (!instancingCandidate(record)) continue;
    let byPass = byGeometry.get(record.geometry);
    if (!byPass) byGeometry.set(record.geometry, (byPass = new Map()));
    const key = recordPassKey(record);
    const group = byPass.get(key) || [];
    group.push(record);
    byPass.set(key, group);
  }
  const sets = new Set();
  for (const byPass of byGeometry.values()) {
    for (const group of byPass.values()) {
      if (group.length < 2) continue;
      const material = group[0].material.clone();
      configureInstanceMaterial(material);
      const object = new THREE.InstancedMesh(group[0].geometry, material, group.length);
      object.name = "CadSurfaceInstances";
      object.castShadow = group[0].mesh.castShadow === true;
      object.receiveShadow = group[0].mesh.receiveShadow === true;
      object.renderOrder = Number(group[0].mesh.renderOrder) || 0;
      object.userData.partIds = group.map((record) => record.partId);
      object.userData.faceIdsByInstance = group.map((record) => record.mesh.userData.faceIds || null);
      // Preserve Three's camera/shadow frustum culling for the whole group.
      // Bound transformed boxes rather than transformed spheres: authored
      // instance matrices may contain nonuniform scale or shear. The shared
      // component geometry stays immutable while this set owns it.
      object.computeBoundingSphere = function () {
        this.computeBoundingBox();
        this.boundingSphere ||= new THREE.Sphere();
        this.boundingBox.getBoundingSphere(this.boundingSphere);
        // Three scales a world sphere by the largest matrix-column length.
        // For an arbitrary affine parent, the true stretch is at most sqrt(3)
        // times that value (the Frobenius bound). This conservative padding
        // also covers external parent shear without a per-frame bounds pass.
        this.boundingSphere.radius *= Math.sqrt(3);
      };
      const set = {
        object,
        records: group,
        disposed: false,
        // The upload attributes already retain the last Float32 values. Use
        // those arrays for dirty checks instead of keeping duplicate mirrors.
        matrixValues: object.instanceMatrix.array,
        colorValues: null,
        materialKey: materialSyncKey(group[0].material),
        groupPassKey: recordPassKey(group[0]),
        activeSlots: new Uint8Array(group.length).fill(1),
        zeroMatrix: new THREE.Matrix4().makeScale(0, 0, 0),
      };
      group.forEach((record, slot) => {
        record.material.visible = false;
        record.mesh.userData.cadSurfaceInstanceProxy = true;
        record.surfaceInstance = { set, slot };
        object.setMatrixAt(slot, record.mesh.matrix);
        const color = record.material.color || record.baseColor || new THREE.Color(0xffffff);
        object.setColorAt(slot, color);
        set.colorValues = object.instanceColor.array;
      });
      object.instanceMatrix.needsUpdate = true;
      if (object.instanceColor) object.instanceColor.needsUpdate = true;
      modelGroup.add(object);
      sets.add(set);
    }
  }
  return sets;
}

function disposeSurfaceInstanceSet(set, modelGroup) {
  if (!set || set.disposed) return;
  if (!set.objectDisposed) { set.object.dispose?.(); set.objectDisposed = true; }
  if (!set.materialDisposed) { set.object.material?.dispose?.(); set.materialDisposed = true; }
  for (const record of set.records) {
    record.surfaceInstance = null;
    record.material.visible = true;
    delete record.mesh.userData.cadSurfaceInstanceProxy;
  }
  (set.object.parent || modelGroup)?.remove(set.object);
  set.disposed = true;
}

export function dissolveCadSurfaceInstanceSets(sets, modelGroup) {
  for (const set of sets || []) {
    // InstancedMesh owns instanceMatrix/instanceColor GPU attributes even
    // though its component geometry is shared. Its dispose event releases
    // those renderer-side buffers without disposing the shared geometry.
    disposeSurfaceInstanceSet(set, modelGroup);
  }
  sets?.clear?.();
}

function setSlotActive(set, record, active) {
  const slot = record.surfaceInstance?.slot;
  if (!Number.isInteger(slot) || set.disposed || Boolean(set.activeSlots[slot]) === active) return;
  set.activeSlots[slot] = active ? 1 : 0;
  record.material.visible = !active;
  if (active) record.mesh.userData.cadSurfaceInstanceProxy = true;
  else delete record.mesh.userData.cadSurfaceInstanceProxy;
  const matrix = active ? record.mesh.matrix : set.zeroMatrix;
  set.object.setMatrixAt(slot, matrix);
  set.object.instanceMatrix.needsUpdate = true;
  set.object.boundingSphere = null;
}

// Reconcile mutable visual state without rebuilding compatible instance
// buffers. Selected/hovered/dimmed records temporarily use their ordinary
// meshes; the unaffected majority stays in the existing InstancedMesh and the
// same slots re-activate when the transient state clears.
export function reconcileCadSurfaceInstanceSets(THREE, records, modelGroup, sets = new Set()) {
  const currentRecords = new Set(records || []);
  const assigned = new Set();
  for (const set of [...sets]) {
    const membershipIntact = set.records.every((record) => (
      currentRecords.has(record) && record.surfaceInstance?.set === set
    ));
    const active = membershipIntact ? set.records.filter((record) => (
      record.geometry === set.object.geometry && instancingCandidate(record)
    )) : [];
    const activePass = active[0] ? recordPassKey(active[0]) : "";
    const compatible = active.length >= 2 && active.every((record) => recordPassKey(record) === activePass);
    if (!membershipIntact || !compatible) {
      disposeSurfaceInstanceSet(set, modelGroup);
      sets.delete(set);
      continue;
    }
    set.groupPassKey = activePass;
    set.object.renderOrder = Number(active[0].mesh.renderOrder) || 0;
    set.object.castShadow = active[0].mesh.castShadow === true;
    set.object.receiveShadow = active[0].mesh.receiveShadow === true;
    const activeSet = new Set(active);
    for (const record of set.records) {
      assigned.add(record);
      setSlotActive(set, record, activeSet.has(record));
    }
    const representative = active[0];
    const nextMaterialKey = materialSyncKey(representative.material);
    if (nextMaterialKey !== set.materialKey) {
      set.object.material.copy(representative.material);
      configureInstanceMaterial(set.object.material);
      set.materialKey = nextMaterialKey;
    }
  }

  const unassigned = (records || []).filter((record) => !assigned.has(record) && instancingCandidate(record));
  for (const set of buildCadSurfaceInstanceSets(THREE, unassigned, modelGroup)) sets.add(set);
  return sets;
}

export function syncCadSurfaceInstanceTransform(record) {
  const instance = record?.surfaceInstance;
  if (!instance || instance.set.disposed) return;
  const { set, slot } = instance;
  if (!set.activeSlots[slot]) return;
  const matrixOffset = slot * 16;
  if (float32Changed(set.matrixValues, matrixOffset, record.mesh.matrix.elements, 16)) {
    set.object.setMatrixAt(slot, record.mesh.matrix);
    set.object.instanceMatrix.needsUpdate = true;
    set.object.boundingSphere = null;
  }
}

export function syncCadSurfaceInstanceRecord(record) {
  const instance = record?.surfaceInstance;
  if (!instance || instance.set.disposed) return;
  const { set, slot } = instance;
  if (!set.activeSlots[slot]) return;
  if (instance.slot === 0) {
    set.object.castShadow = record.mesh.castShadow === true;
    set.object.receiveShadow = record.mesh.receiveShadow === true;
    const nextMaterialKey = materialSyncKey(record.material);
    if (nextMaterialKey !== set.materialKey) {
      set.object.material.copy(record.material);
      configureInstanceMaterial(set.object.material);
      set.materialKey = nextMaterialKey;
    }
  }
  syncCadSurfaceInstanceTransform(record);
  const color = record.material.color || record.baseColor;
  const colorOffset = slot * 3;
  if (set.colorValues[colorOffset] !== Math.fround(color.r) ||
      set.colorValues[colorOffset + 1] !== Math.fround(color.g) ||
      set.colorValues[colorOffset + 2] !== Math.fround(color.b)) {
    set.object.setColorAt(slot, color);
    if (set.object.instanceColor) set.object.instanceColor.needsUpdate = true;
  }
}

import { stepModuleTargetPartIds } from "./stepModule.js";

function toNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function uniqueStrings(values) {
  return [...new Set((Array.isArray(values) ? values : [])
    .map((value) => String(value || "").trim())
    .filter(Boolean))];
}

export function buildPartTransformMatrix(THREE, transform) {
  const matrix = new THREE.Matrix4();
  if (!Array.isArray(transform) || transform.length !== 16) {
    matrix.identity();
    return matrix;
  }
  matrix.set(
    Number(transform[0]) || 0,
    Number(transform[1]) || 0,
    Number(transform[2]) || 0,
    Number(transform[3]) || 0,
    Number(transform[4]) || 0,
    Number(transform[5]) || 0,
    Number(transform[6]) || 0,
    Number(transform[7]) || 0,
    Number(transform[8]) || 0,
    Number(transform[9]) || 0,
    Number(transform[10]) || 0,
    Number(transform[11]) || 0,
    Number(transform[12]) || 0,
    Number(transform[13]) || 0,
    Number(transform[14]) || 0,
    Number(transform[15]) || 0
  );
  return matrix;
}

export function displayTransformForPart(meshData, part, renderPartsIndividually = true) {
  // Composed packages declare partTransformsBaked: false — their shared component
  // geometry is occurrence-local, so the occurrence transform must be applied no
  // matter which render mode is active. Legacy meshDatas leave the flag undefined
  // (vertices world-baked), where per-part transforms only apply in individual mode.
  if (meshData?.partTransformsBaked === false) {
    return part?.transform || null;
  }
  if (!renderPartsIndividually || meshData?.partTransformsBaked === true) {
    return null;
  }
  return part?.transform || null;
}

function normalizeStepModulePoint(value, fallback = [0, 0, 0]) {
  if (Array.isArray(value) || ArrayBuffer.isView(value)) {
    return [
      toNumber(value[0], fallback[0] || 0),
      toNumber(value[1], fallback[1] || 0),
      toNumber(value[2], fallback[2] || 0)
    ];
  }
  if (value && typeof value === "object") {
    return [
      toNumber(value.x, fallback[0] || 0),
      toNumber(value.y, fallback[1] || 0),
      toNumber(value.z, fallback[2] || 0)
    ];
  }
  return [...fallback];
}

function stepModuleVector3(THREE, value, fallback = [0, 0, 0]) {
  const point = normalizeStepModulePoint(value, fallback);
  return new THREE.Vector3(point[0], point[1], point[2]);
}

function buildStepModuleRotateMatrix(THREE, spec = {}) {
  const axis = stepModuleVector3(THREE, spec.axis, [0, 0, 1]);
  if (axis.lengthSq() <= 1e-12) {
    axis.set(0, 0, 1);
  }
  axis.normalize();
  const origin = stepModuleVector3(THREE, spec.origin, [0, 0, 0]);
  const angleRad = Number.isFinite(Number(spec.angleRad))
    ? Number(spec.angleRad)
    : (toNumber(spec.angleDeg, 0) * Math.PI) / 180;
  return new THREE.Matrix4()
    .makeTranslation(origin.x, origin.y, origin.z)
    .multiply(new THREE.Matrix4().makeRotationAxis(axis, angleRad))
    .multiply(new THREE.Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z));
}

function buildStepModuleScaleMatrix(THREE, spec = {}) {
  const rawScale = spec.scale ?? spec;
  const scale = Array.isArray(rawScale) || ArrayBuffer.isView(rawScale)
    ? normalizeStepModulePoint(rawScale, [1, 1, 1])
    : [toNumber(rawScale, 1), toNumber(rawScale, 1), toNumber(rawScale, 1)];
  const origin = stepModuleVector3(THREE, spec.origin, [0, 0, 0]);
  return new THREE.Matrix4()
    .makeTranslation(origin.x, origin.y, origin.z)
    .multiply(new THREE.Matrix4().makeScale(scale[0], scale[1], scale[2]))
    .multiply(new THREE.Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z));
}

function buildStepModuleTranslateMatrix(THREE, value) {
  const translate = normalizeStepModulePoint(value, [0, 0, 0]);
  return new THREE.Matrix4().makeTranslation(translate[0], translate[1], translate[2]);
}

function buildStepModuleSingleEffectMatrix(THREE, spec = {}) {
  if (!spec || typeof spec !== "object") {
    return new THREE.Matrix4();
  }
  if (Array.isArray(spec.matrix) && spec.matrix.length === 16) {
    return buildPartTransformMatrix(THREE, spec.matrix);
  }
  const matrix = new THREE.Matrix4();
  if (spec.scale !== undefined) {
    matrix.premultiply(buildStepModuleScaleMatrix(THREE, spec));
  }
  if (spec.rotate && typeof spec.rotate === "object") {
    matrix.premultiply(buildStepModuleRotateMatrix(THREE, spec.rotate));
  }
  if (spec.translate !== undefined) {
    matrix.premultiply(buildStepModuleTranslateMatrix(THREE, spec.translate));
  }
  return matrix;
}

export function buildStepModuleEffectMatrix(THREE, spec = {}) {
  if (!spec || typeof spec !== "object") {
    return new THREE.Matrix4();
  }
  const steps = Array.isArray(spec.transforms) ? spec.transforms : [spec];
  const matrix = new THREE.Matrix4();
  for (const step of steps) {
    matrix.premultiply(buildStepModuleSingleEffectMatrix(THREE, step));
  }
  return matrix;
}

function matrixHasTransform(matrix, epsilon = 1e-6) {
  if (!matrix?.elements || matrix.elements.length !== 16) {
    return false;
  }
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  return matrix.elements.some((value, index) => Math.abs(Number(value) - identity[index]) > epsilon);
}

export function resetStepModuleRecordEffects(records) {
  for (const record of Array.isArray(records) ? records : []) {
    record.effectMatrix = null;
    record.effectStyle = null;
    record.effectVisible = null;
    record.effectHighlighted = false;
  }
}

function allStepModulePartIds(meshData, displayRecords) {
  const partIds = Array.isArray(meshData?.parts)
    ? meshData.parts.map((part) => String(part?.id || part?.occurrenceId || "").trim()).filter(Boolean)
    : [];
  if (partIds.length) {
    return uniqueStrings(partIds);
  }
  const displayPartIds = (Array.isArray(displayRecords) ? displayRecords : [])
    .map((record) => String(record?.partId || "").trim())
    .filter(Boolean);
  return uniqueStrings(displayPartIds.length ? displayPartIds : ["__model__"]);
}

function resolveStepModuleEffectTargetPartIds(target, features, meshData, displayRecords) {
  if (target && typeof target === "object" && !Array.isArray(target)) {
    if (Array.isArray(target.partIds)) {
      return uniqueStrings(target.partIds);
    }
    if (target.partId) {
      return uniqueStrings([target.partId]);
    }
    if (target.feature) {
      return resolveStepModuleEffectTargetPartIds(target.feature, features, meshData, displayRecords);
    }
    if (target.ref) {
      return stepModuleTargetPartIds(String(target.ref), features, meshData);
    }
  }
  const normalizedTarget = String(target || "").trim();
  if (normalizedTarget === "*" || normalizedTarget === "all" || normalizedTarget === "__all__") {
    return allStepModulePartIds(meshData, displayRecords);
  }
  return stepModuleTargetPartIds(target, features, meshData);
}

export function createStepModuleEffectsApi(THREE, {
  meshData,
  features,
  runtime,
  effectsByPartId,
  onTransformEffect
}) {
  const ensureEffect = (partId) => {
    const id = String(partId || "").trim();
    if (!id) {
      return null;
    }
    const current = effectsByPartId.get(id) || {
      matrix: null,
      style: null,
      visible: null,
      highlighted: false
    };
    effectsByPartId.set(id, current);
    return current;
  };
  const forEachTarget = (target, callback) => {
    const partIds = resolveStepModuleEffectTargetPartIds(target, features, meshData, runtime?.displayRecords);
    for (const partId of partIds) {
      const effect = ensureEffect(partId);
      if (effect) {
        callback(effect, partId);
      }
    }
    return partIds;
  };

  return {
    transform(target, spec) {
      const matrix = buildStepModuleEffectMatrix(THREE, spec);
      const partIds = forEachTarget(target, (effect) => {
        effect.matrix = effect.matrix
          ? effect.matrix.clone().premultiply(matrix)
          : matrix.clone();
      });
      if (partIds.length && matrixHasTransform(matrix)) {
        onTransformEffect?.({
          target,
          spec,
          partIds,
          matrix: matrix.clone()
        });
      }
    },
    style(target, style = {}) {
      if (!style || typeof style !== "object") {
        return;
      }
      forEachTarget(target, (effect) => {
        effect.style = {
          ...(effect.style || {}),
          ...style
        };
      });
    },
    visible(target, visible = true) {
      forEachTarget(target, (effect) => {
        effect.visible = visible !== false;
      });
    },
    highlight(target, highlighted = true) {
      forEachTarget(target, (effect) => {
        effect.highlighted = highlighted !== false;
      });
    },
    clear(target) {
      const partIds = resolveStepModuleEffectTargetPartIds(target, features, meshData, runtime?.displayRecords);
      for (const partId of partIds) {
        effectsByPartId.delete(partId);
      }
    }
  };
}

export function buildStepModuleTimeState(animationState = {}) {
  const duration = Math.max(Number(animationState.duration) || 0, 0);
  const elapsedSec = Math.max(Number(animationState.elapsedSec) || 0, 0);
  return {
    elapsed: elapsedSec,
    elapsedSec,
    duration,
    progress: duration > 0 ? clamp(elapsedSec / duration, 0, 1) : 0,
    cycle: duration > 0 ? elapsedSec / duration : 0,
    playing: animationState.playing === true,
    speed: Math.max(Number(animationState.speed) || 1, 0)
  };
}

export function buildStepModuleContext({
  runtime,
  stepModuleRuntime,
  features,
  effects,
  cleanup
}) {
  const definition = stepModuleRuntime?.definition || null;
  return {
    THREE: runtime?.THREE,
    scene: runtime?.scene,
    modelGroup: runtime?.modelGroup,
    edgesGroup: runtime?.edgesGroup,
    runtime,
    manifest: definition?.manifest || {},
    module: definition?.module || null,
    cadPath: stepModuleRuntime?.cadPath || definition?.cadPath || "",
    params: stepModuleRuntime?.parameterValues || {},
    features,
    effects,
    time: buildStepModuleTimeState(stepModuleRuntime?.animationState),
    cleanup: typeof cleanup === "function" ? cleanup : () => {},
    requestRender: () => runtime?.requestRender?.()
  };
}

export function applyStepModuleEffectsToRecords(THREE, records, effectsByPartId) {
  resetStepModuleRecordEffects(records);
  for (const record of Array.isArray(records) ? records : []) {
    const effect = effectsByPartId.get(String(record?.partId || "").trim());
    if (!effect) {
      continue;
    }
    record.effectMatrix = effect.matrix instanceof THREE.Matrix4 ? effect.matrix.clone() : null;
    record.effectStyle = effect.style && typeof effect.style === "object" ? { ...effect.style } : null;
    record.effectVisible = effect.visible;
    record.effectHighlighted = effect.highlighted === true;
  }
}

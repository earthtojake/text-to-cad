// Viewport LOD scheduler (design/unified-tessellation.md Phase 5).
//
// Non-React glue between camera samples and level-keyed re-tessellation. The
// policy math lives in cadgen-js (lodPolicy.js — pure); this module owns TIME:
// debounce after camera movement, one bounded batch through scene adoption,
// worst projected error first, and cancellation on model replacement. Camera
// changes replan after the accepted replacement finishes. It knows nothing
// about three.js or React: the host feeds camera
// samples and receives level swaps through a callback.

import {
  LOD_CHORD_LEVELS,
  nextLevel,
  normalizeLodLevel,
  projectedChordErrorPx,
  settledLevel,
} from "cadgen-js/lib/surf/lodPolicy.js";

export const LOD_DEBOUNCE_MS = 200;

/**
 * createLodScheduler({
 *   loadLevel(cid, level, { signal }) -> Promise<payload>,
 *   applyLevel(cid, level, payload),
 *   reserveLevel?({ cid, currentLevel, level, direction }) -> { ok, token?, detail? },
 *   releaseLevel?(token),
 *   memoryPressure?() -> boolean,
 *   onLimitation?(detail),
 *   onIdle?({ qualitySettled, unmetTargets, disposed }),
 *   debounceMs?, levels?,
 *   setTimeoutFn?/clearTimeoutFn? (test clocks),
 * })
 *
 * Host contract:
 *  - setComponents([{ cid, diagonal }]) once per model load (resets levels);
 *    `{ preserveLevels: true }` when the SAME model grows (progressive
 *    publish adds components per batch): retained cids keep their level and
 *    an in-flight load for a retained cid keeps running;
 *  - onCameraSample({ camera, viewportHeightPx, distanceFor(cid), cameraKey? })
 *    stamps numeric state and re-arms debounce, returning whether this sample
 *    changed anything the scheduler plans from. A sample that repeats the
 *    previous camera intent AND the previous per-component inputs changes
 *    nothing, so it neither re-arms nor arms the debounce: a host that
 *    resamples a motionless viewport must still be able to reach a settled
 *    state. A stable cameraKey excludes
 *    geometry/accounting changes; only a new key or explicit `{ retry: true }`
 *    clears failures/pressure ceilings. Omitting the key means explicit retry;
 *  - dispose() on unmount.
 */
export function createLodScheduler({
  loadLevel,
  applyLevel,
  applyBatch = null,
  prepareLevel = null,
  needsPreparation = () => false,
  reconcileLevel = null,
  discardLevel = null,
  onOccupiedChanged = null,
  onAdopted = null,
  batchSize = applyBatch ? 4 : 1,
  collectionMs = 32,
  now = () => performance.now(),
  reserveLevel = null,
  releaseLevel = null,
  memoryPressure = () => false,
  onLimitation = null,
  onIdle = null,
  debounceMs = LOD_DEBOUNCE_MS,
  levels = LOD_CHORD_LEVELS,
  minimumLevel = 0,
  setTimeoutFn = (...args) => setTimeout(...args),
  clearTimeoutFn = (handle) => clearTimeout(handle),
} = {}) {
  const components = new Map(); // cid -> { diagonal, level }
  // (cid:level) loads that failed since the last camera/retry epoch. Without this
  // memo a persistently failing load busy-loops the drain (fail -> finally ->
  // re-plan -> same item); with it the failure parks until the camera moves.
  const failed = new Map(); // cid:level -> { reason, detail? }
  // A successful intermediate adoption supplies measured bytes for a new
  // estimate. Only that changed current rung permits another admission check.
  const denied = new Map(); // cid:current:requested -> admission detail
  const pressureCeilings = new Map(); // cid -> highest rung until fresh camera intent
  let sampleEpoch = 0;
  let modelEpoch = 0;
  let lastPressure = false;
  let lastSample = null;
  let timer = null;
  const occupied = new Map(); // distinct CID -> loading / ready / published owner
  const capacity = Math.max(1, Math.min(4, Math.floor(Number(batchSize) || 1)));
  let loading = null;
  let publication = null;
  let collectionTimer = null;
  let sealReason = null;
  let ownershipSerial = 0;
  const transientDenied = new Map(); // reconsider only after another owner settles
  const telemetry = { publicationAttempts: 0, batchSizes: [], sealReasons: {}, maxOccupied: 0,
    collectionMs: 0, adoptionMs: 0 };
  let disposed = false;
  let sceneFailed = false;
  const floorLevel = normalizeLodLevel(minimumLevel);

  function setComponents(list, { preserveLevels = false } = {}) {
    const hadModel = components.size > 0 || lastSample !== null || occupied.size > 0;
    if (!preserveLevels) {
      modelEpoch += 1;
      sceneFailed = false;
      lastSample = null;
      lastPressure = false;
      if (timer !== null) {
        clearTimeoutFn(timer);
        timer = null;
      }
      failed.clear();
      denied.clear();
      pressureCeilings.clear();
    }
    const previous = preserveLevels ? new Map(components) : null;
    components.clear();
    for (const { cid, diagonal, level } of list || []) {
      if (cid && Number.isFinite(diagonal) && diagonal > 0) {
        components.set(cid, {
          diagonal,
          level: previous?.get(cid)?.level ?? normalizeLodLevel(level),
        });
      }
    }
    // A model switch cancels stale work; a growing model keeps a load whose
    // component is still present (its level would otherwise be re-requested,
    // or a finer displayed level re-stepped through a coarser one).
    if (!preserveLevels) cancelOccupied();
    else for (const task of occupied.values()) if (!components.has(task.cid)) cancelTask(task);
    if (!preserveLevels && hadModel && occupied.size === 0) onIdle?.(qualityStatus());
    if (preserveLevels && lastSample && timer === null && occupied.size === 0) {
      timer = setTimeoutFn(() => { timer = null; evaluate(); }, debounceMs);
    }
  }

  function changed() {
    telemetry.maxOccupied = Math.max(telemetry.maxOccupied, occupied.size);
    onOccupiedChanged?.([...occupied.values()].map(({ cid, level, payload, status }) => ({ cid, level, payload, status })));
  }

  function releaseTask(task, discard = false, notify = true) {
    if (occupied.get(task.cid) !== task) return;
    try { if (discard && task.payload) discardLevel?.(task.cid, task.level, task.payload); }
    finally {
      for (const token of task.reservations) releaseLevel?.(token);
      task.reservations = [];
      task.payload = null;
      task.measuredPayload = null;
      occupied.delete(task.cid);
      ownershipSerial++; // only an actual owner release reopens temporary denials
      if (![...occupied.values()].some(owner => owner.status !== "published" && owner.readyAt !== undefined && !owner.controller.signal.aborted)) {
        if (collectionTimer !== null) clearTimeoutFn(collectionTimer);
        collectionTimer = null;
      }
      if (notify) changed();
    }
  }

  function cancelTask(task) {
    task.controller.abort();
    if (task.status === "published") publication?.controller.abort();
    else if (loading !== task) releaseTask(task, true);
  }

  function cancelOccupied() {
    if (collectionTimer !== null) clearTimeoutFn(collectionTimer);
    collectionTimer = null; sealReason = null;
    for (const task of [...occupied.values()]) cancelTask(task);
  }

  // Same camera intent AND the same numbers for every component: the next
  // evaluation would replan exactly what the last one already planned. Hosts
  // build a new sample object per notification, so object identity says
  // nothing; the planning inputs do.
  function planningInputsChanged(sample) {
    if (!lastSample) return true;
    for (const cid of components.keys()) {
      if (!Object.is(sample.distanceFor(cid), lastSample.distanceFor(cid))) return true;
      if ((sample.visibleFor?.(cid) !== false) !== (lastSample.visibleFor?.(cid) !== false)) return true;
      if ((sample.selectedFor?.(cid) === true) !== (lastSample.selectedFor?.(cid) === true)) return true;
    }
    return false;
  }

  function onCameraSample(sample, { retry = false } = {}) {
    if (disposed) {
      return false;
    }
    // Hosts supply cameraKey from camera/viewport state, excluding component
    // bounds. Publication/accounting resamples must not restart pressure loops.
    // An omitted key preserves the explicit-camera-call contract for hosts
    // without automatic resampling; retry is an explicit external intent.
    const fresh = !lastSample || retry || !Object.hasOwn(sample, "cameraKey") || sample.cameraKey !== lastSample.cameraKey;
    // A repeated sample is not new work. Re-arming the debounce for it would
    // hold `pendingEvaluation` — and therefore `qualitySettled` — false for as
    // long as the host keeps resampling a motionless viewport.
    const changed = fresh || planningInputsChanged(sample);
    lastSample = sample;
    if (fresh) {
      sampleEpoch += 1;
      failed.clear();
      denied.clear();
      pressureCeilings.clear();
      if (occupied.size) sealReason = "camera";
    }
    if (changed) {
      if (timer !== null) {
        clearTimeoutFn(timer);
      }
      timer = setTimeoutFn(() => {
        timer = null;
        evaluate();
      }, debounceMs);
    }
    if (fresh && occupied.size) pump();
    return changed;
  }

  function entriesForPlan() {
    const entries = [];
    for (const [cid, state] of components) {
      const cameraDistance = lastSample.distanceFor(cid);
      if (!Number.isFinite(cameraDistance)) {
        continue;
      }
      entries.push({
        cid,
        currentLevel: state.level,
        visible: lastSample.visibleFor?.(cid) !== false,
        selected: lastSample.selectedFor?.(cid) === true,
        sample: {
          diagonal: state.diagonal,
          cameraDistance,
          camera: lastSample.camera,
          viewportHeightPx: lastSample.viewportHeightPx,
        },
      });
    }
    return entries;
  }

  function blocked(cid, currentLevel, level) {
    return failed.has(`${cid}:${level}`) || denied.has(`${cid}:${currentLevel}:${level}`);
  }

  function availableLevel(cid, currentLevel, targetLevel) {
    // All endpoints come from normalized component/policy levels. Prefer the
    // target, then strictly intermediate rungs, without same-state retries.
    const direction = Math.sign(targetLevel - currentLevel);
    if (!direction) return null;
    for (let level = targetLevel; level !== currentLevel; level -= direction) {
      if (level >= floorLevel && !blocked(cid, currentLevel, level)) return level;
    }
    return null;
  }

  function qualityStatus(entries = lastSample ? entriesForPlan() : [], pressure = lastPressure) {
    const eligible = entries.filter((entry) => entry.visible);
    const unmetTargets = [];
    for (const entry of eligible) {
      const cid = entry.cid;
      const state = components.get(cid);
      if (!state) continue;
      const cameraTargetLevel = Math.max(floorLevel, settledLevel(entry.sample, state.level, levels));
      const blockedCoarsen = pressure && state.level > floorLevel && blocked(cid, state.level, state.level - 1);
      const targetLevel = blockedCoarsen ? state.level - 1 : cameraTargetLevel;
      if (targetLevel === state.level) continue;
      let blockedLevel = targetLevel;
      // The legacy floor path can require a blocked intermediate before the
      // final floor is even attempted (e.g. offscreen L0 -> L1 -> floor L2).
      if (state.level < floorLevel && !blocked(cid, state.level, targetLevel) && blocked(cid, state.level, state.level + 1)) {
        blockedLevel = state.level + 1;
      }
      const detail = denied.get(`${cid}:${state.level}:${blockedLevel}`);
      const failure = failed.get(`${cid}:${blockedLevel}`);
      const ceiling = pressureCeilings.get(cid);
      const pressureLimited = (blockedCoarsen && !detail) || (pressure && targetLevel > state.level) ||
        (ceiling !== undefined && targetLevel > ceiling);
      const reason = pressureLimited ? "memory-pressure"
        : failure?.reason || (detail ? "memory-denied" : "pending");
      unmetTargets.push({ cid, currentLevel: state.level, targetLevel, reason,
        ...(blockedCoarsen ? { cameraTargetLevel } : {}),
        ...(ceiling !== undefined ? { pressureCeiling: ceiling } : {}),
        ...(blockedLevel !== targetLevel ? { blockedLevel } : {}),
        ...(detail || failure?.detail ? { detail: detail || failure.detail } : {}) });
    }
    const belowMinimum = eligible.filter(({ currentLevel }) => currentLevel < floorLevel).length;
    return {
      scope: "visible-components",
      eligibleComponentCount: eligible.length,
      belowMinimum,
      qualitySettled: !disposed && !sceneFailed && !!lastSample && occupied.size === 0 && timer === null && collectionTimer === null && unmetTargets.length === 0,
      standardSettled: !disposed && !sceneFailed && !!lastSample && belowMinimum === 0,
      sceneFailed,
      memoryPressure: pressure,
      unmetTargets,
      disposed,
    };
  }

  function failureDetail(error) {
    if (!error) return null;
    if (typeof error === "string") return { message: error };
    if (typeof error !== "object") return { message: String(error) };
    const message = String(error.message || "LOD operation failed");
    const name = String(error.name || "Error");
    return { name, message };
  }

  function parkFailure(task, reason, error = null) {
    if (!disposed && !task.controller.signal.aborted &&
        task.modelEpoch === modelEpoch && task.sampleEpoch === sampleEpoch) {
      const detail = failureDetail(error);
      failed.set(`${task.cid}:${task.level}`, { cid: task.cid, level: task.level, reason,
        ...(detail ? { detail } : {}) });
    }
  }

  function planWork(entries, pressure) {
    const plan = [];
    for (const entry of entries) {
      if (occupied.has(entry.cid)) continue;
      if (!entry.visible) continue;
      const policyLevel = pressure
        ? nextLevel(entry.sample, entry.currentLevel, levels)
        : settledLevel(entry.sample, entry.currentLevel, levels);
      const targetLevel = Math.max(floorLevel, policyLevel);
      if (targetLevel === entry.currentLevel) continue;
      const admittedTarget = !pressure && targetLevel > entry.currentLevel
        ? Math.min(targetLevel, pressureCeilings.get(entry.cid) ?? targetLevel) : targetLevel;
      const level = pressure
        ? (blocked(entry.cid, entry.currentLevel, targetLevel) ? null : targetLevel)
        : availableLevel(entry.cid, entry.currentLevel, admittedTarget);
      if (level === null || level === entry.currentLevel || (pressure && level > entry.currentLevel)) continue;
      plan.push({ cid: entry.cid, level, targetLevel, visible: true, selected: entry.selected, errorPx: projectedChordErrorPx({
        ...entry.sample, chordRel: levels[entry.currentLevel],
      }) });
    }
    plan.sort((a, b) => Number(b.selected) - Number(a.selected) || b.errorPx - a.errorPx);
    if (pressure) {
      const planned = new Set(plan.map((item) => `${item.cid}:${item.level}`));
      for (const entry of entries) {
        if (occupied.has(entry.cid)) continue;
        if (entry.currentLevel <= floorLevel) continue;
        const level = entry.currentLevel - 1;
        const key = `${entry.cid}:${level}`;
        if (!planned.has(key) && !blocked(entry.cid, entry.currentLevel, level)) {
          plan.push({
            cid: entry.cid,
            level,
            targetLevel: level,
            visible: entry.visible,
            selected: entry.selected,
            errorPx: entry.visible ? projectedChordErrorPx({
              ...entry.sample,
              chordRel: levels[entry.currentLevel],
            }) : 0,
          });
        }
      }
    }
    if (pressure) {
      // A downgrade releases retained detail. Under pressure it must run
      // before a visually useful but memory-increasing refinement.
      plan.sort((a, b) => {
        const aCurrent = components.get(a.cid)?.level ?? 0;
        const bCurrent = components.get(b.cid)?.level ?? 0;
        const aCoarsens = aCurrent > a.level;
        const bCoarsens = bCurrent > b.level;
        if (aCoarsens !== bCoarsens) return aCoarsens ? -1 : 1;
        if (!aCoarsens) return Number(b.selected) - Number(a.selected) || b.errorPx - a.errorPx;
        return Number(a.visible) - Number(b.visible) || Number(a.selected) - Number(b.selected) || a.errorPx - b.errorPx;
      });
    }
    return plan;
  }

  function evaluate() { pump(); }

  function readyTasks() {
    return [...occupied.values()].filter(task => task.status === "ready" && !task.forcePreparation && !needsPreparation(task.cid, task.level, task.payload));
  }

  function armDeadline() {
    if (collectionTimer !== null || sealReason) return;
    const ready = [...occupied.values()].filter(task => task.status === "ready");
    if (!ready.length) return;
    const first = Math.min(...ready.map(task => task.readyAt));
    collectionTimer = setTimeoutFn(() => {
      collectionTimer = null; sealReason = "deadline"; pump();
    }, Math.max(0, first + collectionMs - now()));
  }

  function valid(task) {
    return !disposed && !task.controller.signal.aborted && task.modelEpoch === modelEpoch && occupied.get(task.cid) === task;
  }

  function loadFailed(task, reason = "load-failed", error = null) {
    if (occupied.get(task.cid) !== task) return;
    parkFailure(task, reason, error);
    releaseTask(task, true);
    sealReason ||= "failure";
  }

  function measurePayload(task, payload) {
    if (!valid(task)) { task.payload = payload; releaseTask(task, true); return false; }
    if (task.measuredPayload === payload) return true;
    task.payload = payload;
    changed(); // staged buffers are excluded from cache accounting before top-up
    const adjustment = reconcileLevel?.({ cid: task.cid, level: task.level, currentLevel: task.currentLevel,
      payload, reservedBytes: task.reservedBytes, pressure: task.pressure }) || { ok: true };
    if (adjustment.ok === false) {
      const hasOtherOwners = occupied.size > 1;
      releaseTask(task, true);
      if (hasOtherOwners) transientDenied.set(task.cid, ownershipSerial);
      else {
        denied.set(`${task.cid}:${task.currentLevel}:${task.level}`, adjustment.detail || {});
        if (task.visible !== false) onLimitation?.(adjustment.detail || {
          cid: task.cid, level: task.level, preservingCurrentView: true,
        });
      }
      sealReason ||= "admission";
      return false;
    }
    if (adjustment.token) task.reservations.push(adjustment.token);
    task.reservedBytes += Number(adjustment.bytes) || 0;
    task.measuredPayload = payload;
    return true;
  }

  function finishPrepared(task, payload) {
    if (occupied.get(task.cid) !== task) return;
    if (!measurePayload(task, payload)) return;
    task.status = "ready";
    task.forcePreparation = false;
    task.readyAt ??= now();
    if (task.sampleEpoch !== sampleEpoch) sealReason ||= "camera";
    if (task.pressure) sealReason ||= "pressure";
    changed(); armDeadline();
  }

  function runLoader(task, preparing = false) {
    loading = task;
    task.status = "loading";
    changed();
    let operation;
    try {
      operation = preparing ? task.payload : loadLevel(task.cid, task.level, { signal: task.controller.signal });
    } catch (error) { operation = Promise.reject(error); }
    Promise.resolve(operation).then(payload => {
      if (!measurePayload(task, payload)) return payload;
      return prepareLevel ? prepareLevel(task.cid, task.level, payload, { signal: task.controller.signal }) : payload;
    }).then(payload => {
      finishPrepared(task, payload);
    }).catch((error) => loadFailed(task, "load-failed", error)).finally(() => {
      if (loading === task) loading = null;
      pump();
    });
  }

  function publishReady(reason) {
    const tasks = readyTasks();
    if (!tasks.length || publication) return false;
    if (collectionTimer !== null) clearTimeoutFn(collectionTimer);
    collectionTimer = null; sealReason = null;
    const controller = new AbortController();
    const owner = { tasks, controller, modelEpoch, startedAt: now() };
    publication = owner;
    tasks.forEach(task => { task.status = "published"; });
    changed();
    telemetry.publicationAttempts++;
    telemetry.batchSizes.push(tasks.length);
    if (telemetry.batchSizes.length > 64) telemetry.batchSizes.shift();
    telemetry.sealReasons[reason] = (telemetry.sealReasons[reason] || 0) + 1;
    telemetry.collectionMs += Math.max(0, now() - Math.min(...tasks.map(task => task.readyAt)));
    let result;
    try {
      const entries = tasks.map(({ cid, level, payload }) => ({ cid, level, payload }));
      result = applyBatch ? applyBatch(entries, { signal: controller.signal })
        : applyLevel(tasks[0].cid, tasks[0].level, tasks[0].payload, { signal: controller.signal });
    } catch (error) { result = Promise.reject(error); }
    Promise.resolve(result).then(outcome => {
      if (outcome?.status === "not-ready" && !controller.signal.aborted && owner.modelEpoch === modelEpoch) {
        for (const task of tasks) {
          task.preflightRetries = (task.preflightRetries || 0) + 1;
          if (task.preflightRetries > 1) { parkFailure(task, "adoption-refused"); releaseTask(task, true); }
          else { task.status = "ready"; task.forcePreparation = true; }
        }
        return;
      }
      const currentOwner = !disposed && !controller.signal.aborted && owner.modelEpoch === modelEpoch;
      if (currentOwner && outcome?.status === "scene-failed") sceneFailed = true;
      const retained = outcome?.status === "retained";
      const accepted = currentOwner && !retained && outcome !== false && outcome?.status !== "scene-failed";
      for (const task of tasks) {
        if (accepted && valid(task)) {
          const current = components.get(task.cid);
          if (current) current.level = task.level;
          if (task.pressure && task.level < task.currentLevel && task.sampleEpoch === sampleEpoch)
            pressureCeilings.set(task.cid, Math.max(floorLevel, Math.min(pressureCeilings.get(task.cid) ?? task.level, task.level)));
        } else if (currentOwner) parkFailure(task,
          outcome?.status === "scene-failed" ? "scene-failed" : "adoption-refused",
          outcome?.error || outcome?.detail);
      }
      try { if (accepted) onAdopted?.(tasks.map(({ cid, level }) => ({ cid, level })), outcome); }
      finally { for (const task of tasks) releaseTask(task, !accepted && !retained, false); changed(); }
    }).catch((error) => {
      for (const task of tasks) { parkFailure(task, "load-failed", error); releaseTask(task, true, false); }
      changed();
    }).finally(() => {
      telemetry.adoptionMs += Math.max(0, now() - owner.startedAt);
      if (publication === owner) publication = null;
      if (sceneFailed) for (const task of [...occupied.values()]) cancelTask(task);
      pump();
    });
    return true;
  }

  function pump() {
    if (publication) return;
    if (disposed || sceneFailed || !lastSample) {
      if (!occupied.size) onIdle?.(qualityStatus());
      return;
    }
    const ready = readyTasks();
    if (ready.length && (sealReason || ready.length >= capacity || ready.some(task => task.pressure))) {
      publishReady(sealReason || "capacity"); return;
    }
    if (loading) return;
    // Changed selector demand takes the SAME lane as render loading. It does
    // not create another loader or spend another occupied slot.
    const stale = [...occupied.values()].find(task => task.status === "ready" && (task.forcePreparation || needsPreparation(task.cid, task.level, task.payload)));
    if (stale) { runLoader(stale, true); return; }
    if (timer !== null) return; // fresh camera intent must settle before collecting more
    if (!occupied.size) { transientDenied.clear(); sealReason = null; }
    if (occupied.size >= capacity) { publishReady("capacity"); return; }
    while (!disposed && !loading && !publication) {
      const entries = entriesForPlan();
      const pressure = occupied.size ? false : memoryPressure?.() === true;
      if (!occupied.size) lastPressure = pressure;
      const request = planWork(entries, pressure).find(item => transientDenied.get(item.cid) !== ownershipSerial);
      if (!request) {
        if (readyTasks().length) publishReady("no-work");
        else if (!occupied.size) onIdle?.(qualityStatus(entries, pressure));
        return;
      }
      const { cid, level, targetLevel } = request;
      const currentLevel = components.get(cid)?.level ?? 0;
      const direction = level < currentLevel ? "coarsen" : "refine";
      const reservation = reserveLevel?.({ cid, currentLevel, level, direction }) ?? { ok: true };
      if (reservation.ok === false) {
        if (occupied.size) {
          transientDenied.set(cid, ownershipSerial);
          publishReady("admission");
          return;
        }
        denied.set(`${cid}:${currentLevel}:${level}`, reservation.detail || {});
        if (request.visible !== false) onLimitation?.({ ...(reservation.detail || {}), cid, currentLevel, level, targetLevel, preservingCurrentView: true });
        continue;
      }
      const task = { cid, level, currentLevel, pressure, visible: request.visible,
        controller: new AbortController(), sampleEpoch, modelEpoch,
        reservations: reservation.token ? [reservation.token] : [], reservedBytes: Number(reservation.bytes) || 0,
        status: "loading", payload: null };
      occupied.set(cid, task);
      runLoader(task);
      return;
    }
  }

  function dispose() {
    disposed = true;
    if (timer !== null) {
      clearTimeoutFn(timer);
      timer = null;
    }
    cancelOccupied();
    if (occupied.size === 0) onIdle?.(qualityStatus());
  }

  return {
    setComponents,
    onCameraSample,
    dispose,
    // Introspection for tests and debugging overlays.
    levelOf: (cid) => components.get(cid)?.level ?? null,
    busy: () => occupied.size > 0,
    snapshot: () => ({
      componentCount: components.size,
      occupied: occupied.size, loading: Number(!!loading), ready: [...occupied.values()].filter(task => task.status === "ready").length,
      adopting: publication?.tasks.length || 0, capacity, collectionPending: collectionTimer !== null,
      batching: { ownershipScope: "scheduler-replacements", loaderLanes: 1, independentSelectorsIncluded: false, ...telemetry, batchSizes: [...telemetry.batchSizes], sealReasons: { ...telemetry.sealReasons } },
      levelCounts: [...components.values()].reduce((counts, state) => {
        counts[state.level] = (counts[state.level] || 0) + 1;
        return counts;
      }, {}),
      minimumLevel: floorLevel,
      busy: occupied.size > 0,
      pendingEvaluation: timer !== null,
      failedLevels: failed.size,
      failures: [...failed.values()].map((failure) => ({ ...failure })),
      deniedAttempts: denied.size,
      pressureLimitedComponents: pressureCeilings.size,
      ...qualityStatus(),
    }),
  };
}

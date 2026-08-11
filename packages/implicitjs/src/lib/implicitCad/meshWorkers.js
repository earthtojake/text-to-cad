/**
 * The parallel implicit mesher: `meshImplicitCadModel` over `worker_threads`.
 *
 * Baking every model at resolution 96 is what makes the implicit render package possible, and
 * a single-threaded bake is minutes per model. Both loops parallelize over `iz`:
 *
 * * **sample** writes disjoint plane blocks of the field array (a SharedArrayBuffer, so no
 *   copy and no merge);
 * * **polygonize** reads planes `iz` and `iz+1` read-only and appends to its own output, so
 *   concatenating chunk outputs in chunk order reproduces the serial pass byte for byte.
 *
 * A barrier separates the two: polygonizing slab `iz` needs sample plane `iz+1`.
 *
 * **The output is identical to the serial mesher, not merely equivalent** -- pinned by a test.
 * The only per-worker state is the smooth-normal cache, and `estimateGradient` is pure, so a
 * vertex touched by two workers is computed twice and yields the same number both times.
 *
 * Node-only (`node:worker_threads`); the browser render path never meshes on the CPU.
 */

import os from "node:os";
import { Worker } from "node:worker_threads";
import { fileURLToPath } from "node:url";

import {
  cellPlaneCount,
  implicitCadGrid,
  meshImplicitCadModel,
  meshNormalEpsilon,
  samplePlaneCount,
  sampledValueCount,
} from "./mesh.js";
import { normalizeImplicitCadModel } from "./model.js";

const WORKER_ENTRY = fileURLToPath(new URL("./meshWorkerEntry.js", import.meta.url));

// Chunks per worker. More than one so a worker that draws a run of empty slabs (polygonizing
// is wildly non-uniform -- most of a bounding box is not near the surface) comes back for
// more work instead of finishing early and idling.
const CHUNKS_PER_WORKER = 6;

export function defaultThreadCount() {
  const available = typeof os.availableParallelism === "function"
    ? os.availableParallelism()
    : os.cpus().length;
  return Math.max(1, Number.isFinite(available) ? available : 1);
}

function normalizeThreads(value) {
  const numeric = Math.floor(Number(value));
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return defaultThreadCount();
  }
  return numeric;
}

/** Contiguous, ascending `[from, to)` plane ranges covering `[0, count)`. */
function planeChunks(count, chunkCount) {
  const chunks = [];
  const size = Math.max(1, Math.ceil(count / Math.max(1, chunkCount)));
  for (let from = 0; from < count; from += size) {
    chunks.push({ chunk: chunks.length, from, to: Math.min(from + size, count) });
  }
  return chunks;
}

/**
 * The data-only slice of a normalized model an SDF evaluator needs.
 *
 * Verified structuredClone-able: `glslSource` is a string and every uniform value is a
 * number, boolean or number array. The model itself is NOT clone-able (its definition holds
 * closures), which is why this exists.
 */
export function sdfEvaluatorPayload(model) {
  return { glslSource: model.glslSource, uniforms: model.uniforms };
}

function concatFloat32(parts, total) {
  const out = new Float32Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

/**
 * Run `chunks` across `workers`, one outstanding chunk per worker, until all are done.
 *
 * Dynamic rather than a static split because polygonizing is wildly non-uniform: a worker
 * handed the empty half of a bounding box would finish in milliseconds and then idle.
 *
 * Listeners are attached for the duration of ONE phase and removed on settle. Leaving them
 * attached would make the next phase's plane reports also count against this phase's
 * progress -- both phases post the same `plane` message.
 */
function runChunks(workers, chunks, { type, onPlane, onResult, extra = {} }) {
  return new Promise((resolve, reject) => {
    let next = 0;
    let outstanding = 0;
    let settled = false;
    const listeners = [];

    const detach = () => {
      for (const [worker, event, handler] of listeners) {
        worker.off(event, handler);
      }
      listeners.length = 0;
    };
    const finish = () => {
      if (settled) return;
      settled = true;
      detach();
      resolve();
    };
    const fail = (error) => {
      if (settled) return;
      settled = true;
      detach();
      reject(error instanceof Error ? error : new Error(String(error)));
    };

    const pump = (worker) => {
      if (settled) return;
      if (next >= chunks.length) {
        if (outstanding === 0) {
          finish();
        }
        return;
      }
      const chunk = chunks[next];
      next += 1;
      outstanding += 1;
      worker.postMessage({ type, ...extra, ...chunk });
    };

    for (const worker of workers) {
      const onMessage = (message) => {
        if (message?.type === "plane") {
          onPlane?.();
          return;
        }
        if (message?.type === "sampled" || message?.type === "polygonized") {
          outstanding -= 1;
          onResult?.(message);
          pump(worker);
        }
      };
      worker.on("error", fail);
      worker.on("message", onMessage);
      listeners.push([worker, "error", fail], [worker, "message", onMessage]);
    }
    if (!chunks.length) {
      finish();
      return;
    }
    for (const worker of workers) {
      pump(worker);
    }
  });
}

/**
 * Mesh `modelValue` using `threads` worker threads.
 *
 * `onSamplePlane` / `onPolygonizePlane` fire once per completed plane, in no particular
 * order -- they are progress counters against a denominator the caller already knows
 * (`planeCounts`), not a position in the grid.
 */
export async function meshImplicitCadModelParallel(modelValue, options = {}) {
  const model = normalizeImplicitCadModel(modelValue);
  const threads = normalizeThreads(options.threads);
  const grid = implicitCadGrid(model, options);
  const normalEpsilon = meshNormalEpsilon(model, options);
  const polygonizeOptions = {
    orientByGradient: options.orientByGradient === true,
    orientBySdf: options.orientBySdf !== false,
    smoothNormals: options.smoothNormals === true,
    snapFeatures: options.snapFeatures !== false,
  };

  if (threads <= 1) {
    // Not a degraded path: the serial mesher IS the reference implementation, and one thread
    // has nothing to gain from the worker machinery's marshalling.
    const mesh = meshImplicitCadModel(model, options);
    options.onSamplePlane?.(samplePlaneCount(grid));
    options.onPolygonizePlane?.(cellPlaneCount(grid));
    return mesh;
  }

  const values = new Float32Array(
    new SharedArrayBuffer(sampledValueCount(grid) * Float32Array.BYTES_PER_ELEMENT)
  );
  const workers = Array.from({ length: threads }, () => new Worker(WORKER_ENTRY, {
    workerData: {
      evaluatorPayload: sdfEvaluatorPayload(model),
      grid,
      values: values.buffer,
      normalEpsilon,
      polygonizeOptions,
    },
  }));

  try {
    const chunksPerWorker = Math.max(1, Math.floor(Number(options.chunksPerWorker) || CHUNKS_PER_WORKER));
    await runChunks(workers, planeChunks(samplePlaneCount(grid), threads * chunksPerWorker), {
      type: "sample",
      onPlane: () => options.onSamplePlane?.(1),
    });

    const slabChunks = planeChunks(cellPlaneCount(grid), threads * chunksPerWorker);
    const outputs = new Array(slabChunks.length);
    // Decided HERE, once, now that the shared field is fully sampled -- not inside a worker.
    // Two workers measuring their own slabs could disagree about the same model and split its
    // surface between a refined and an unrefined solve, which would both tear the mesh and
    // break the byte-identity the serial pass is checked against.
    const refineEdges = options.refineEdges !== false;
    await runChunks(workers, slabChunks, {
      type: "polygonize",
      extra: { refineEdges },
      onPlane: () => options.onPolygonizePlane?.(1),
      onResult: (message) => {
        outputs[message.chunk] = message;
      },
    });

    // Chunk order, not completion order: this is what makes the output byte-identical to the
    // serial pass rather than merely a permutation of the same triangles.
    const total = outputs.reduce((sum, part) => sum + part.positions.length, 0);
    const positions = concatFloat32(outputs.map((part) => part.positions), total);
    const normals = concatFloat32(outputs.map((part) => part.normals), total);
    return {
      positions,
      normals,
      format: "triangle-list",
      sourceModel: model,
      grid: {
        resolution: [grid.nx, grid.ny, grid.nz],
        step: grid.step,
      },
      vertexCount: positions.length / 3,
      triangleCount: positions.length / 9,
    };
  } finally {
    await Promise.all(workers.map((worker) => worker.terminate()));
  }
}

/** The two determinate progress denominators a bake reports, known before any work starts. */
export function planeCounts(model, options = {}) {
  const grid = implicitCadGrid(normalizeImplicitCadModel(model), options);
  return { sample: samplePlaneCount(grid), polygonize: cellPlaneCount(grid) };
}

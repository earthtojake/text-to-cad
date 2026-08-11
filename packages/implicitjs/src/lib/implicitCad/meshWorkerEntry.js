/**
 * One worker of the parallel implicit mesher (`meshWorkers.js`).
 *
 * A worker cannot be handed the SDF closure -- it is a JS function compiled from the model's
 * GLSL and functions do not survive `structuredClone` -- so each worker builds its OWN
 * evaluator from the data-only payload (`glslSource` + `uniforms`) the parent extracted from
 * the normalized model. That is the whole reason this file exists: everything else it does is
 * `mesh.js`'s own exported passes, called on a range of planes.
 *
 * The sampled field lives in a SharedArrayBuffer. Sampling writes disjoint plane blocks, so
 * no synchronisation is needed beyond the parent's barrier between the two phases.
 */

import { parentPort, workerData } from "node:worker_threads";

import { polygonizeCellPlanes, sampleFieldPlanes } from "./mesh.js";
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

const { evaluatorPayload, grid, values: sharedValues, normalEpsilon, polygonizeOptions } = workerData;

const sdf = createImplicitCadSdfEvaluator(evaluatorPayload);
const values = new Float32Array(sharedValues);

parentPort.on("message", (message) => {
  const reportPlane = () => parentPort.postMessage({ type: "plane" });
  if (message?.type === "sample") {
    sampleFieldPlanes(sdf, grid, values, {
      from: message.from,
      to: message.to,
      onPlane: reportPlane,
    });
    parentPort.postMessage({ type: "sampled", chunk: message.chunk });
    return;
  }
  if (message?.type === "polygonize") {
    const { positions, normals } = polygonizeCellPlanes(sdf, grid, values, {
      ...polygonizeOptions,
      normalEpsilon,
      // Sent per message, not baked into workerData: it is only knowable after the shared
      // sample pass finishes, which is after these workers were constructed.
      refineEdges: message.refineEdges !== false,
      from: message.from,
      to: message.to,
      onPlane: reportPlane,
    });
    parentPort.postMessage(
      { type: "polygonized", chunk: message.chunk, positions, normals },
      [positions.buffer, normals.buffer]
    );
    return;
  }
  if (message?.type === "stop") {
    parentPort.close();
  }
});

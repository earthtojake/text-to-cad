import { readCadWorkerTicket } from "../../client/resources.js";
import { buildMeshDataFromStlBuffer } from "./stlMeshData.js";
import { withStlBodies } from "./stlBodies.js";
import { meshDataTransferList } from "./meshTransfer.js";

const activeControllers = new Map();

self.addEventListener("message", async (event) => {
  const message = event.data || {};
  const id = message.id;
  if (!id) {
    return;
  }

  if (message.type === "cancel") {
    activeControllers.get(id)?.abort();
    activeControllers.delete(id);
    return;
  }

  // An STL's bodies, after the model shows (`loadStlBodies`): its own copy of the triangles, put in body order.
  if (message.type === "stlBodies") {
    try {
      const { vertices, normals, parts } = withStlBodies({ vertices: message.vertices, normals: message.normals }, message.solids || []);
      const transfer = [...new Set([vertices.buffer, normals.buffer])];
      self.postMessage({ id, ok: true, bodies: { vertices, normals, parts } }, transfer);
    } catch (error) {
      self.postMessage({ id, ok: false, error: { name: error?.name || "Error", message: error instanceof Error ? error.message : String(error) } });
    }
    return;
  }

  if (message.type !== "loadStl") {
    return;
  }

  const controller = new AbortController();
  activeControllers.set(id, controller);
  try {
    const buffer = await readCadWorkerTicket(message.resource, { signal: controller.signal });
    const meshData = await buildMeshDataFromStlBuffer(buffer);
    if (controller.signal.aborted) {
      return;
    }
    self.postMessage(
      { id, ok: true, meshData },
      meshDataTransferList(meshData)
    );
  } catch (error) {
    if (!controller.signal.aborted) {
      self.postMessage({
        id,
        ok: false,
        error: {
          name: error?.name || "Error",
          message: error instanceof Error ? error.message : String(error)
        }
      });
    }
  } finally {
    activeControllers.delete(id);
  }
});

import { readCadWorkerTicket } from "../../client/resources.js";
import { buildMeshDataFromGlbBuffer } from "./glbMeshData.js";
import { meshDataTransferList } from "./meshTransfer.js";

const activeControllers = new Map();
const resourceRequests = new Map();
let nextResourceId = 1;
function nestedResources(id, signal) {
  return {
    resolveDependency: (_source, reference) => reference,
    readBytes(reference) {
      return new Promise((resolve, reject) => {
        const resourceId = nextResourceId++;
        const abort = () => { resourceRequests.delete(resourceId); reject(signal.reason); };
        signal.addEventListener("abort", abort, { once: true });
        resourceRequests.set(resourceId, { resolve, reject, cleanup: () => signal.removeEventListener("abort", abort) });
        self.postMessage({ type: "resource", id, resourceId, reference });
      });
    },
  };
}

self.addEventListener("message", async (event) => {
  const message = event.data || {};
  if (message.type === "resource") {
    const pending = resourceRequests.get(message.resourceId);
    if (pending) {
      resourceRequests.delete(message.resourceId); pending.cleanup();
      if (message.error) pending.reject(new Error(message.error)); else pending.resolve(message.bytes);
    }
    return;
  }
  const id = message.id;
  if (!id) {
    return;
  }

  if (message.type === "cancel") {
    activeControllers.get(id)?.abort();
    activeControllers.delete(id);
    return;
  }

  if (message.type !== "loadGlb") {
    return;
  }

  const controller = new AbortController();
  activeControllers.set(id, controller);
  try {
    const buffer = await readCadWorkerTicket(message.resource, { signal: controller.signal });
    const meshData = await buildMeshDataFromGlbBuffer(buffer, { resources: nestedResources(id, controller.signal), signal: controller.signal });
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

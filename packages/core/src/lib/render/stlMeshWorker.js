import { readCadWorkerTicket } from "../../client/resources.js";
import { buildMeshDataFromStlBuffer } from "./stlMeshData.js";
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

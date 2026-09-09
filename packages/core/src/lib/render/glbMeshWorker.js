import { buildMeshDataFromGlbBuffer } from "./glbMeshData.js";
import { meshDataTransferList } from "./meshTransfer.js";

const activeControllers = new Map();

function fetchError(url, response) {
  return new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
}

async function loadArrayBuffer(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw fetchError(url, response);
  }
  return response.arrayBuffer();
}

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

  if (message.type !== "loadGlb") {
    return;
  }

  const controller = new AbortController();
  activeControllers.set(id, controller);
  try {
    const buffer = await loadArrayBuffer(message.url, controller.signal);
    const meshData = await buildMeshDataFromGlbBuffer(buffer);
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

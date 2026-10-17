import { readCadWorkerTicket } from "../../client/resources.js";
// Part worker.
//
// One request = one part's stored mesh (bytes the client thread read and
// verified) and an explicit capability set. Ordinary display asks only for
// render data, which the mesh alone carries; picking/measurement asks for
// selectors, which also read the part's selector table (cadgen's, its record's
// other object) and join it to the mesh. Decoding, copying into render-owned
// arrays and the join run here, off the page's main thread.

import { buildComponentMeshData } from "./partMeshData.js";
import { joinSelectorTable, parseSelectorTable } from "./selectorTable.js";
import { meshDataTransferList } from "../render/meshTransfer.js";
import { decodeComponentTessellation } from "./tessellationCache.js";

const activeControllers = new Map();

function bundleTransferList(bundle) {
  return Object.values(bundle?.buffers || {})
    .map((view) => view?.buffer)
    .filter((buffer) => buffer instanceof ArrayBuffer && buffer.byteLength > 0);
}

function requestedCapabilities(message) {
  const value = message?.capabilities;
  if (!value || typeof value !== "object") {
    return { render: true, selectors: true };
  }
  return {
    render: value.render === true,
    selectors: value.selectors === true,
  };
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
  if (message.type !== "loadPart") {
    return;
  }
  const controller = new AbortController();
  activeControllers.set(id, controller);
  try {
    const capabilities = requestedCapabilities(message);
    if (!capabilities.render && !capabilities.selectors) {
      throw new Error("Part worker request has no capabilities");
    }
    const cached = decodeComponentTessellation(message.cachedEntry, { part: String(message.part || "") });
    if (!cached) {
      throw new Error("Part worker request carries no readable mesh for this component");
    }
    const meshData = capabilities.render ? buildComponentMeshData(cached.component) : null;
    let bundle = null;
    if (capabilities.selectors) {
      const buffer = await readCadWorkerTicket(message.resource, { signal: controller.signal });
      bundle = joinSelectorTable(parseSelectorTable(buffer), cached.component);
    }
    if (controller.signal.aborted) {
      return;
    }
    self.postMessage(
      {
        id,
        ok: true,
        ...(meshData ? { meshData } : {}),
        ...(bundle ? { bundle } : {}),
      },
      [...new Set([
        ...(meshData ? meshDataTransferList(meshData) : []),
        ...bundleTransferList(bundle),
      ])],
    );
  } catch (error) {
    if (!controller.signal.aborted) {
      self.postMessage({
        id,
        ok: false,
        error: {
          name: error?.name || "Error",
          message: error instanceof Error ? error.message : String(error),
        },
      });
    }
  } finally {
    activeControllers.delete(id);
  }
});

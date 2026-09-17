import { buildSerializedRaycastBvh, raycastBvhResultTransfers } from "./raycastBvhBuild.js";

self.onmessage = ({ data }) => {
  try {
    const serialized = buildSerializedRaycastBvh(data);
    self.postMessage({ serialized }, raycastBvhResultTransfers(serialized));
  } catch (error) {
    self.postMessage({ error: error?.message || String(error) });
  }
};

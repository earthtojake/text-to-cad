import { SurfaceResolutionError } from "@text-to-cad/core/client";
export { SurfaceResolutionError };

export function resolveSurfaceComponents(descriptor, requested, { signal, client, onReady, onFailed, onPending, tessellation } = {}) {
  if (!client?.resolveSurfaceComponents) throw new TypeError("Surface resolution requires a CAD workspace service");
  return client.resolveSurfaceComponents(descriptor, requested, {
    signal, ...(onReady ? { onReady } : {}), ...(onFailed ? { onFailed } : {}), ...(onPending ? { onPending } : {}),
    ...(tessellation != null ? { tessellation } : {}),
  });
}

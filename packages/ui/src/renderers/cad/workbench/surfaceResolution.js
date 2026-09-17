import { SurfaceResolutionError } from "@hardcore/core/client";
export { SurfaceResolutionError };

export function resolveSurfaceComponents(descriptor, requested, { signal, client } = {}) {
  if (!client?.resolveSurfaceComponents) throw new TypeError("Surface resolution requires a CAD workspace service");
  return client.resolveSurfaceComponents(descriptor, requested, { signal });
}

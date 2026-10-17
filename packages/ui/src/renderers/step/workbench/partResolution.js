import { PartResolutionError } from "@text-to-cad/core/client";
export { PartResolutionError };

export function resolveParts(descriptor, requested, { signal, client, onReady, onFailed, onPending } = {}) {
  if (!client?.resolveParts) throw new TypeError("Part resolution requires a CAD workspace service");
  return client.resolveParts(descriptor, requested, {
    signal, ...(onReady ? { onReady } : {}), ...(onFailed ? { onFailed } : {}), ...(onPending ? { onPending } : {}),
  });
}

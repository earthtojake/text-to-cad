import { surfTessellationCacheKey } from "@hardcore/core/lib/renderAssetClient.js";
import { lodTessellationForLevel, normalizeLodLevel } from "@hardcore/core/lib/surf/lodPolicy.js";

export function lodPayloadRequest(component, level) {
  return Object.freeze({ descriptor: component.descriptor, file: component.file,
    cid: component.cid, baseMesh: component.meshData, baseLevel: component.level, identity: component.identity, url: component.surfUrl,
    key: surfTessellationCacheKey(component.surfUrl, lodTessellationForLevel(level), component.identity) });
}

export function matchesLodPayloadRequest(request, context, cid, level, url) {
  const identity = context?.componentIdentityByCid?.[cid] || context?.descriptor?.components?.[cid];
  return !!request && request.descriptor === context?.descriptor && request.file === context?.file &&
    request.cid === cid && !!request.baseMesh && context.componentMeshDataByCid?.[cid] === request.baseMesh &&
    normalizeLodLevel(context.componentLodLevelByCid?.[cid]) === normalizeLodLevel(request.baseLevel) && request.identity === identity && request.url === url &&
    request.key === surfTessellationCacheKey(url, lodTessellationForLevel(level), identity);
}

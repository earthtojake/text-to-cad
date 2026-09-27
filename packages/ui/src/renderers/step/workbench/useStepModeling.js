import { entryAssetUrl } from '@text-to-cad/core/lib/entryAssets.js';
import { useModelingRecognition } from './useModelingRecognition.js';

/** Read-only STEP inspection: feature recognition for the Features tree. */
export function useStepModeling(entry, enabled, options) {
  return useModelingRecognition(entryAssetUrl(entry, 'glb'), enabled, { ...options, entry });
}

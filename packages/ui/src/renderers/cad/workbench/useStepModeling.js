import { entryAssetUrl } from '@hardcore/core/lib/entryAssets.js';
import { useModelingRecognition } from './useModelingRecognition.js';

/** Read-only STEP inspection survives inspector tab switches. */
export function useStepModeling(entry, enabled) {
  return useModelingRecognition(entryAssetUrl(entry, 'glb'), enabled);
}

export {
  definePluginCapability,
  type AnyPluginCapability,
  type CapabilityBehaviors,
  type CapabilityDescriptors,
  type CapabilityMap,
  type InferPluginBehaviorType,
  type InferPluginDescriptorType,
  type ResolvedCapabilityDescriptors,
} from './capability';
export {
  definePluginAsset,
  type AnyPluginAsset,
  type AssetDescriptors,
  type AssetMap,
  type InferPluginAssetType,
} from './asset';
export { createPluginFramework } from './framework';
export { createPluginRegistry, type PluginRegistry } from './registry';
export { iconAsset, type PluginIconAsset, type PluginIconVariant } from './icon';

import type z from 'zod';
import type { AssetDescriptors, AssetMap } from './asset';
import type {
  CapabilityBehaviors,
  CapabilityDescriptors,
  CapabilityMap,
  ResolvedCapabilityDescriptors,
} from './capability';

/**
 * Create a plugin framework bound to a fixed capability map, metadata schema,
 * and asset map.
 *
 * The capability and asset maps are passed as values so their precise types
 * are inferred, which makes the descriptor record, the asset record
 * (definePlugin), and the behavior record (registerPluginBehavior) exactly
 * typed per slot key.
 */
export function createPluginFramework<
  TCaps extends CapabilityMap,
  TMetaSchema extends z.ZodType,
  TAssets extends AssetMap,
>(capabilityMap: TCaps, metadataSchema: TMetaSchema, assetMap: TAssets) {
  type TMeta = z.output<TMetaSchema>;

  function definePlugin(
    metadata: TMeta,
    capabilities: CapabilityDescriptors<TCaps>,
    assets: AssetDescriptors<TAssets>
  ) {
    const resolved = {} as ResolvedCapabilityDescriptors<TCaps>;
    for (const key of Object.keys(capabilityMap) as (keyof TCaps)[]) {
      const provided = (capabilities as Record<keyof TCaps, unknown>)[key];
      const raw = provided !== undefined ? provided : capabilityMap[key].defaultDescriptor;
      const parsed = capabilityMap[key].descriptorSchema.safeParse(raw);
      (resolved as Record<keyof TCaps, unknown>)[key] = parsed.success ? parsed.data : raw;
    }

    return {
      metadata,
      capabilities: resolved,
      assets,
      validate(): z.ZodError[] {
        const metaResult = metadataSchema.safeParse(metadata);
        if (!metaResult.success) return [metaResult.error];
        return [
          ...Object.entries(capabilityMap).flatMap(([key, cap]) => {
            const result = cap.descriptorSchema.safeParse(resolved[key as keyof TCaps]);
            return result.success ? [] : [result.error];
          }),
          ...Object.entries(assetMap).flatMap(([key, asset]) => {
            const result = asset.assetSchema.safeParse(assets[key as keyof TAssets]);
            return result.success ? [] : [result.error];
          }),
        ];
      },
    };
  }

  type PluginDefinition = ReturnType<typeof definePlugin>;

  function registerPluginBehavior(plugin: PluginDefinition, behavior: CapabilityBehaviors<TCaps>) {
    for (const key of Object.keys(capabilityMap) as (keyof TCaps)[]) {
      const capability = capabilityMap[key];
      if (!capability.requiresBehavior) continue;

      const descriptor = plugin.capabilities[key];
      const behaviorForCapability = behavior[key as keyof CapabilityBehaviors<TCaps>];
      if (capability.requiresBehavior(descriptor) && behaviorForCapability === undefined) {
        const metadata = plugin.metadata as { id?: unknown };
        const pluginId = typeof metadata.id === 'string' ? metadata.id : '<unknown>';
        throw new Error(
          `Plugin '${pluginId}' declares capability '${capability.id}' that requires behavior, but no behavior was registered.`
        );
      }
    }

    return { ...plugin, behavior };
  }

  return { definePlugin, registerPluginBehavior };
}

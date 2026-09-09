import type z from 'zod';

/**
 * Define a plugin asset: a stable id and a Zod schema for the serializable
 * asset data. Assets are pure data (no functions, no components) so they can
 * be validated, bundled as plain constants, and sent over IPC.
 *
 *   const iconAsset = definePluginAsset('icon', iconSchema);
 */
export function definePluginAsset<TId extends string, TSchema extends z.ZodType>(
  id: TId,
  assetSchema: TSchema
) {
  return {
    id,
    assetSchema,
    _asset: undefined as z.output<TSchema>,
  };
}

/** Structural shape of any asset produced by definePluginAsset. */
export type AnyPluginAsset = {
  id: string;
  assetSchema: z.ZodType;
  _asset: unknown;
};

export type AssetMap = Record<string, AnyPluginAsset>;

/** What definePlugin accepts for assets: every asset slot, declaratively. */
export type AssetDescriptors<TAssets extends AssetMap> = {
  [K in keyof TAssets]: TAssets[K]['_asset'];
};

export type InferPluginAssetType<TAsset> = TAsset extends { _asset: infer T } ? T : never;

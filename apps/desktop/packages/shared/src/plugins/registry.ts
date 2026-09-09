export type PluginRegistry<TPlugin extends { metadata: { id: string } }> = {
  register(plugin: TPlugin): void;
  get(id: string): TPlugin | undefined;
  getAll(): TPlugin[];
  ids(): string[];
};

export function createPluginRegistry<
  TPlugin extends { metadata: { id: string } },
>(): PluginRegistry<TPlugin> {
  const plugins = new Map<string, TPlugin>();
  return {
    register(plugin: TPlugin) {
      plugins.set(plugin.metadata.id, plugin);
    },
    get: (id: string) => plugins.get(id),
    getAll: () => [...plugins.values()],
    ids: () => [...plugins.keys()],
  };
}

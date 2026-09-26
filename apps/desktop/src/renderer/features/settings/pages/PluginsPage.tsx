/**
 * Plugins: what the base app is running with. One row per plugin the build carries, on or off as
 * `HARDCORE_PLUGINS` set it at launch, with what each adds — the files it opens, the skills it
 * hands to agents and the agent tools it brings (src/plugins/README.md).
 */
import { SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { cn } from "@renderer/lib/utils";
import { usePlugins } from "@renderer/state/plugins";
import type { PluginInfo } from "@shared/ipc/plugins";

export function PluginsPage() {
  const plugins = usePlugins((state) => state.plugins);
  const on = plugins.filter((plugin) => plugin.enabled);
  return (
    <>
      <SettingCard title="This run">
        <SettingRow
          description={on.length
            ? `The base app plus ${on.map((plugin) => plugin.name).join(", ")}. Set HARDCORE_PLUGINS before launching to change it: none for the base app alone, or a comma list of ids.`
            : "The base app alone: chat with agents, files, terminals, the browser and the generic viewers. Set HARDCORE_PLUGINS=all (or a comma list of ids) before launching to add plugins."}
          keywords="HARDCORE_PLUGINS base app extensions"
          title={on.length ? `${on.length} of ${plugins.length} plugins on` : "Base app only"}
        />
      </SettingCard>
      <SettingCard title="In this build">
        {plugins.map((plugin) => <PluginRow key={plugin.id} plugin={plugin} />)}
      </SettingCard>
    </>
  );
}

function PluginRow({ plugin }: { plugin: PluginInfo }) {
  return (
    <SettingRow
      control={
        <span className={cn("rounded-full px-2 py-0.5 text-xs", plugin.enabled ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground")}>
          {plugin.enabled ? "On" : "Off"}
        </span>
      }
      description={plugin.description}
      keywords={[plugin.id, ...plugin.extensions, ...plugin.skills, ...plugin.tools].join(" ")}
      title={`${plugin.name} (${plugin.id})`}
    >
      <dl className="grid grid-cols-[5rem_1fr] gap-x-3 gap-y-1 text-xs">
        <Facet label="Opens" values={plugin.extensions.map((extension) => `.${extension}`)} />
        <Facet label="Skills" values={plugin.skills} />
        <Facet label="Tools" values={plugin.tools} />
      </dl>
    </SettingRow>
  );
}

function Facet({ label, values }: { label: string; values: string[] }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono break-words">{values.length ? values.join(", ") : "—"}</dd>
    </>
  );
}

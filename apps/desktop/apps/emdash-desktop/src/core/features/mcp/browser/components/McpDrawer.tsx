import type { HostRef } from '@emdash/core/primitives/host/api';
import type {
  McpCatalogEntry,
  McpProvidersResponse,
  McpServer,
} from '@emdash/core/primitives/mcp/api';
import { Button, Field, Input, MicroLabel, Select, Sheet } from '@emdash/ui/react/primitives';
import { useForm } from '@tanstack/react-form';
import { Trash2 } from 'lucide-react';
import React, { useLayoutEffect, useRef, useState } from 'react';
import { modalScope } from '@core/features/workbench/contributions/scopes';
import { confirmRegistry } from '@core/primitives/keybindings/browser';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { scopes } from '@core/primitives/view-scopes/browser';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';
import { KeyValueSection, type KVEntry } from './KeyValueSection';
import { SyncToAgentsSection } from './SyncToAgentsSection';

export type McpDrawerMode =
  | { type: 'add-catalog'; entry: McpCatalogEntry }
  | { type: 'add-custom' }
  | { type: 'edit'; server: McpServer };

interface McpDrawerProps {
  open: boolean;
  mode: McpDrawerMode | null;
  host: HostRef;
  providers: McpProvidersResponse[];
  onOpenChange: (open: boolean) => void;
  onSave: (server: McpServer) => Promise<void>;
  onRemove?: (serverName: string) => void;
}

export const McpDrawer: React.FC<McpDrawerProps> = ({
  open,
  mode,
  host,
  providers,
  onOpenChange,
  onSave,
  onRemove,
}) => {
  const implementation = {
    'modal.close': () => ({ execute: () => onOpenChange(false) }),
    'app.confirm': () => ({
      availability: () => (confirmRegistry.current?.isEnabled() ? enabled : hidden),
      execute: () => confirmRegistry.current?.trigger(),
    }),
  } satisfies ViewScopeImpl<typeof modalScope>;
  const { attachRef, instance } = useViewScope(modalScope(), implementation);

  useLayoutEffect(() => {
    if (!open || !instance) return;
    return scopes.activateCapture(instance);
  }, [instance, open]);

  return (
    <Sheet.Root open={open} onOpenChange={onOpenChange}>
      <Sheet.Content ref={attachRef} side="right" className="gap-0 p-0">
        <ViewScopeInstanceProvider instance={instance}>
          {mode && (
            <McpDrawerContent
              mode={mode}
              host={host}
              providers={providers}
              onOpenChange={onOpenChange}
              onSave={onSave}
              onRemove={onRemove}
            />
          )}
        </ViewScopeInstanceProvider>
      </Sheet.Content>
    </Sheet.Root>
  );
};

interface McpDrawerContentProps {
  mode: McpDrawerMode;
  host: HostRef;
  providers: McpProvidersResponse[];
  onOpenChange: (open: boolean) => void;
  onSave: (server: McpServer) => Promise<void>;
  onRemove?: (serverName: string) => void;
}

const McpDrawerContent: React.FC<McpDrawerContentProps> = ({
  mode,
  host,
  providers,
  onOpenChange,
  onSave,
  onRemove,
}) => {
  const isEdit = mode.type === 'edit';
  const isCatalog = mode.type === 'add-catalog';
  const credentialKeys = isCatalog
    ? new Map(mode.entry.credentialKeys.map((c) => [c.key, c.required]))
    : new Map<string, boolean>();

  const nextId = useRef(0);
  const makeId = () => nextId.current++;

  const toKV = (entries: [string, string][]): KVEntry[] =>
    entries.map(([k, v]) => ({ id: makeId(), key: k, value: v }));

  const initial = getInitialState(mode);
  const [saving, setSaving] = useState(false);

  const form = useForm({
    defaultValues: {
      name: initial.name,
      transport: initial.transport,
      command: initial.command,
      args: initial.args,
      url: initial.url,
      envEntries: toKV(initial.env),
      headerEntries: toKV(initial.headers),
      selectedProviders: initial.providers,
    },
  });

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const v = form.state.values;
      const filledHeaders = v.headerEntries.filter((e) => e.key && e.value);
      const filledEnv = v.envEntries.filter((e) => e.key && e.value);
      const server: McpServer = {
        name: v.name,
        transport: v.transport,
        command: v.transport === 'stdio' ? v.command : undefined,
        args:
          v.transport === 'stdio' && v.args.trim()
            ? v.args.split('\n').filter((a) => a.length > 0)
            : undefined,
        url: v.transport === 'http' ? v.url : undefined,
        headers: filledHeaders.length
          ? Object.fromEntries(filledHeaders.map((e) => [e.key, e.value]))
          : undefined,
        env: filledEnv.length
          ? Object.fromEntries(filledEnv.map((e) => [e.key, e.value]))
          : undefined,
        providers: v.selectedProviders,
      };
      await onSave(server);
      onOpenChange(false);
    } catch {
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Sheet.Header>
        <MicroLabel>MCP Server</MicroLabel>
        <Sheet.Title>
          {isEdit
            ? 'Edit MCP Server'
            : isCatalog
              ? `Add ${form.state.values.name}`
              : 'Add Custom MCP Server'}
        </Sheet.Title>
      </Sheet.Header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        {isCatalog && mode.entry.description && (
          <p className="mb-4 text-xs text-foreground-muted">{mode.entry.description}</p>
        )}
        <Field.Group>
          <form.Field name="name">
            {(field) => (
              <Field.Root>
                <Field.Label>Server Name</Field.Label>
                <Input
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  disabled={isCatalog || isEdit}
                  placeholder="my-server"
                />
              </Field.Root>
            )}
          </form.Field>

          {!isCatalog && (
            <form.Field name="transport">
              {(field) => (
                <Field.Root>
                  <Field.Label>Transport</Field.Label>
                  <Select.Root
                    value={field.state.value}
                    onValueChange={(v) => {
                      const next = v as 'stdio' | 'http';
                      field.handleChange(next);
                    }}
                  >
                    <Select.Trigger>
                      <Select.Value />
                    </Select.Trigger>
                    <Select.Content>
                      <Select.Item value="stdio">stdio</Select.Item>
                      <Select.Item value="http">http</Select.Item>
                    </Select.Content>
                  </Select.Root>
                </Field.Root>
              )}
            </form.Field>
          )}

          <form.Subscribe selector={(state) => state.values.transport}>
            {(transport) => (
              <>
                {transport === 'stdio' && (
                  <>
                    <form.Field name="command">
                      {(field) => (
                        <Field.Root>
                          <Field.Label>Command</Field.Label>
                          <Input
                            value={field.state.value}
                            onChange={(e) => field.handleChange(e.target.value)}
                            disabled={isCatalog}
                            placeholder="npx"
                          />
                        </Field.Root>
                      )}
                    </form.Field>
                    <form.Field name="args">
                      {(field) => (
                        <Field.Root>
                          <Field.Label>Arguments (one per line)</Field.Label>
                          <textarea
                            value={field.state.value}
                            onChange={(e) => field.handleChange(e.target.value)}
                            disabled={isCatalog}
                            placeholder={'-y\nmy-mcp-server'}
                            rows={3}
                            className="flex w-full rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-foreground-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                          />
                        </Field.Root>
                      )}
                    </form.Field>
                  </>
                )}

                {transport === 'http' && (
                  <form.Field name="url">
                    {(field) => (
                      <Field.Root>
                        <Field.Label>URL</Field.Label>
                        <Input
                          value={field.state.value}
                          onChange={(e) => field.handleChange(e.target.value)}
                          disabled={isCatalog}
                          placeholder="https://mcp.example.com"
                        />
                      </Field.Root>
                    )}
                  </form.Field>
                )}
              </>
            )}
          </form.Subscribe>

          <form.Field name="envEntries">
            {(field) => (
              <KeyValueSection
                label="Environment Variables"
                entries={field.state.value}
                onChange={(entries) => field.handleChange(entries)}
                addLabel="+ Add env var"
                makeId={makeId}
                credentialKeys={credentialKeys}
                splitEnvPaste
              />
            )}
          </form.Field>

          <form.Subscribe selector={(state) => state.values.transport}>
            {(transport) =>
              transport === 'http' && (
                <form.Field name="headerEntries">
                  {(field) => (
                    <KeyValueSection
                      label="Headers"
                      entries={field.state.value}
                      onChange={(entries) => field.handleChange(entries)}
                      addLabel="+ Add header"
                      makeId={makeId}
                      credentialKeys={credentialKeys}
                    />
                  )}
                </form.Field>
              )
            }
          </form.Subscribe>

          <form.Field name="selectedProviders">
            {(field) => (
              <SyncToAgentsSection
                host={host}
                providers={providers}
                selectedProviders={field.state.value}
                onToggle={(id) => {
                  field.handleChange(
                    field.state.value.includes(id)
                      ? field.state.value.filter((value) => value !== id)
                      : [...field.state.value, id]
                  );
                }}
                onSetAll={(ids) => field.handleChange(ids)}
              />
            )}
          </form.Field>
        </Field.Group>
      </div>

      <Sheet.Footer className="flex-row items-center justify-between gap-2 sm:flex-row">
        {isEdit && onRemove ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-foreground-destructive hover:text-foreground-destructive"
            onClick={() => onRemove(form.state.values.name)}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Remove
          </Button>
        ) : (
          <span />
        )}
        <form.Subscribe selector={(state) => state.values}>
          {(values) => {
            const canSave =
              !!values.name.trim() &&
              !saving &&
              values.selectedProviders.length > 0 &&
              !!(values.transport === 'http' ? values.url.trim() : values.command.trim());
            return (
              <ConfirmButton
                variant="primary"
                type="button"
                onClick={() => void handleSave()}
                disabled={!canSave}
                size="sm"
              >
                {saving ? (isEdit ? 'Saving...' : 'Adding...') : isEdit ? 'Save' : 'Add'}
              </ConfirmButton>
            );
          }}
        </form.Subscribe>
      </Sheet.Footer>
    </>
  );
};

function getInitialState(mode: McpDrawerMode) {
  if (mode.type === 'edit') {
    const s = mode.server;
    return {
      name: s.name,
      transport: s.transport,
      command: s.command ?? '',
      args: s.args?.join('\n') ?? '',
      url: s.url ?? '',
      env: Object.entries(s.env ?? {}),
      headers: Object.entries(s.headers ?? {}),
      providers: s.providers,
    };
  }
  if (mode.type === 'add-catalog') {
    const cfg = mode.entry.defaultConfig;
    const isHttp = cfg.type === 'http' || ('url' in cfg && !('command' in cfg));
    const clearPlaceholders = (entries: [string, string][]): [string, string][] =>
      entries.map(([k, v]) => [k, typeof v === 'string' && v.includes('YOUR_') ? '' : v]);
    return {
      name: mode.entry.key,
      transport: (isHttp ? 'http' : 'stdio') as 'stdio' | 'http',
      command: (cfg.command as string) ?? '',
      args: Array.isArray(cfg.args) ? (cfg.args as string[]).join('\n') : '',
      url: (cfg.url as string) ?? '',
      env: clearPlaceholders(Object.entries((cfg.env as Record<string, string>) ?? {})),
      headers: clearPlaceholders(Object.entries((cfg.headers as Record<string, string>) ?? {})),
      providers: [] as string[],
    };
  }
  return {
    name: '',
    transport: 'stdio' as const,
    command: '',
    args: '',
    url: '',
    env: [] as [string, string][],
    headers: [] as [string, string][],
    providers: [] as string[],
  };
}

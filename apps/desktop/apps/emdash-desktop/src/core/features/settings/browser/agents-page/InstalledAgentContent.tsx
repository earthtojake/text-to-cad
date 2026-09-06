import { Button, Collapsible, Field, Input, Label, Tooltip } from '@emdash/ui/react/primitives';
import { useForm } from '@tanstack/react-form';
import { ChevronRight, Info, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import React, { useCallback, useEffect, useState } from 'react';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';
import {
  parseEnvAssignmentPaste,
  replaceEnvEntryWithPaste,
} from '@core/primitives/env-paste/browser/env-paste';
import { log } from '@core/primitives/logging/browser/logger';
import { cn } from '@core/primitives/styling/browser/cn';

type EnvEntry = { key: string; value: string };

const FieldTooltip: React.FC<{ content: string }> = ({ content }) => (
  <Tooltip.Provider>
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            className="text-foreground-muted hover:text-foreground"
            aria-label="More information"
          >
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        }
      />
      <Tooltip.Content side="top" className="max-w-[200px] text-xs">
        {content}
      </Tooltip.Content>
    </Tooltip.Root>
  </Tooltip.Provider>
);

export interface InstalledAgentContentProps {
  storedConfig: ProviderCustomConfig | undefined;
  isOverridden: boolean;
  isLoading: boolean;
  update: (
    cfg: ProviderCustomConfig,
    opts?: { onSuccess?: () => void; onError?: (e: unknown) => void }
  ) => void;
  reset: (
    val?: undefined,
    opts?: { onSuccess?: () => void; onError?: (e: unknown) => void }
  ) => void;
}

function makeDefaultValues(cfg: ProviderCustomConfig | undefined) {
  return {
    extraArgs: cfg?.extraArgs ?? '',
    envEntries: cfg?.env
      ? (Object.entries(cfg.env).map(([key, value]) => ({ key, value })) as EnvEntry[])
      : ([] as EnvEntry[]),
  };
}

export const InstalledAgentContent = observer(function InstalledAgentContent({
  storedConfig,
  isOverridden,
  isLoading,
  update,
  reset,
}: InstalledAgentContentProps) {
  const [open, setOpen] = useState(false);

  const form = useForm({ defaultValues: makeDefaultValues(storedConfig) });

  // Re-sync form when external config changes (e.g. after a reset from outside).
  useEffect(() => {
    if (isLoading) return;
    const next = makeDefaultValues(storedConfig);
    form.setFieldValue('extraArgs', next.extraArgs);
    form.setFieldValue('envEntries', next.envEntries);
  }, [isLoading, storedConfig, isOverridden, form]);

  const commit = useCallback(() => {
    const { extraArgs, envEntries } = form.state.values;
    const envRecord: Record<string, string> = {};
    for (const { key, value } of envEntries) {
      const k = key.trim();
      if (k && /^[A-Za-z_]\w*$/.test(k)) {
        envRecord[k] = value;
      }
    }

    const isAtDefaults = extraArgs.trim() === '' && envEntries.every((e) => !e.key.trim());

    if (isAtDefaults) {
      reset(undefined, {
        onError: (err) => log.error('Failed to reset agent config:', err),
      });
    } else {
      const config: ProviderCustomConfig = {
        ...(storedConfig ?? {}),
        extraArgs: extraArgs.trim() || undefined,
        env: Object.keys(envRecord).length > 0 ? envRecord : undefined,
      };
      update(config, {
        onError: (err) => log.error('Failed to save agent config:', err),
      });
    }
  }, [form, storedConfig, reset, update]);

  const handleResetToDefaults = useCallback(() => {
    form.setFieldValue('extraArgs', '');
    form.setFieldValue('envEntries', []);
    reset(undefined, {
      onError: (err) => log.error('Failed to reset agent config:', err),
    });
  }, [form, reset]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-2">
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <Collapsible.Trigger
          hideChevron
          type="button"
          className="flex w-full items-center justify-between rounded-md py-2 text-sm font-medium text-foreground-muted hover:text-foreground"
        >
          <span className="flex h-6 items-center gap-1.5">
            <Label>Advanced settings</Label>
            <ChevronRight
              className={cn('size-3.5', 'transition-transform', open ? 'rotate-90' : '')}
            />
          </span>
          {isOverridden && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 gap-1.5 px-2 text-xs"
              onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                e.stopPropagation();
                handleResetToDefaults();
              }}
            >
              <RotateCcw className="size-3.5" />
              Reset to defaults
            </Button>
          )}
        </Collapsible.Trigger>

        <Collapsible.Panel className="space-y-4 rounded-lg border p-3">
          {/* Additional parameters */}
          <form.Field name="extraArgs">
            {(field) => (
              <Field.Root>
                <div className="flex items-center gap-2">
                  <Label htmlFor="sheet-extraArgs">Additional parameters</Label>
                  <FieldTooltip content="Extra flags appended to the command (e.g. --enable-all-github-mcp-tools)" />
                </div>
                <Input
                  id="sheet-extraArgs"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  onBlur={() => commit()}
                  placeholder="e.g. --enable-all-github-mcp-tools"
                  className="font-mono text-sm"
                />
              </Field.Root>
            )}
          </form.Field>

          {/* Environment variables */}
          <form.Field name="envEntries">
            {(field) => (
              <Field.Root>
                <div className="flex items-center gap-2">
                  <Label>Environment variables</Label>
                  <FieldTooltip content="Environment variables set when running the agent" />
                </div>
                <div className="space-y-2">
                  {field.state.value.map((entry, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input
                        value={entry.key}
                        placeholder="KEY"
                        className="min-w-0 flex-1 font-mono text-sm"
                        onChange={(e) =>
                          field.handleChange(
                            field.state.value.map((v, idx) =>
                              idx === i ? { ...v, key: e.target.value } : v
                            )
                          )
                        }
                        onBlur={() => commit()}
                        onPaste={(e) => {
                          const pasted = parseEnvAssignmentPaste(e.clipboardData.getData('text'));
                          if (pasted.length === 0) return;
                          e.preventDefault();
                          field.handleChange(
                            replaceEnvEntryWithPaste(field.state.value, i, pasted)
                          );
                        }}
                      />
                      <Input
                        value={entry.value}
                        placeholder="value"
                        className="min-w-0 flex-1 font-mono text-sm"
                        onChange={(e) =>
                          field.handleChange(
                            field.state.value.map((v, idx) =>
                              idx === i ? { ...v, value: e.target.value } : v
                            )
                          )
                        }
                        onBlur={() => commit()}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        icon
                        className="h-8 w-8 shrink-0"
                        aria-label="Remove"
                        onClick={() => {
                          field.handleChange(field.state.value.filter((_, idx) => idx !== i));
                          commit();
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="gap-1.5"
                    onClick={() =>
                      field.handleChange([...field.state.value, { key: '', value: '' }])
                    }
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add variable
                  </Button>
                </div>
              </Field.Root>
            )}
          </form.Field>

          {isOverridden && (
            <div className="rounded-md border border-border-warning bg-background-warning px-3 py-2 text-xs text-foreground-warning">
              Custom configuration is applied
            </div>
          )}
        </Collapsible.Panel>
      </Collapsible.Root>
    </div>
  );
});

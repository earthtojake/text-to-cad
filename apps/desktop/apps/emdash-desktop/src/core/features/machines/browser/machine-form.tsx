import { ComboboxPopover } from '@emdash/ui/react/components';
import { FormFieldShell, useAppForm, useFieldContext } from '@emdash/ui/react/form';
import { Button, Collapsible, Tooltip } from '@emdash/ui/react/primitives';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  InfoIcon,
  LoaderCircle,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import type { ConnectionTestResult, SshConfig, SshConfigHost } from '@core/primitives/ssh/api';
import { suggestedAuthTypeForSshConfigHost, type MachineAuthType } from './machine-form-model';
import { machineFormSchema } from './machine-form-schema';
import { useSshConfigHost, useSshConfigHosts } from './use-ssh-config-hosts';

type TestState = 'idle' | 'testing' | 'success' | 'error';

const MANUAL_CONNECTION_VALUE = '__manual__';
const EMPTY_SSH_CONFIG_HOSTS: SshConfigHost[] = [];
const DUPLICATE_CONNECTION_NAME_ERROR =
  'An SSH connection with this name already exists. Choose a different name.';

function formatMachineError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const withoutIpcPrefix = message.replace(/^Error invoking remote method 'ssh\.[^']+':\s*/, '');

  if (/UNIQUE constraint failed: ssh_connections\.name/.test(withoutIpcPrefix)) {
    return DUPLICATE_CONNECTION_NAME_ERROR;
  }

  return withoutIpcPrefix;
}

function FieldInfoTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            className="relative inline-flex size-4 shrink-0 items-center justify-center rounded-full text-foreground-passive transition-colors before:absolute before:-inset-2.5 before:content-[''] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none"
            aria-label={`About ${label}`}
          >
            <InfoIcon className="size-3.5" aria-hidden="true" />
          </button>
        }
      />
      <Tooltip.Content
        side="top"
        align="start"
        className="max-w-[240px] items-start text-left leading-relaxed whitespace-normal"
      >
        {children}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}

function FieldLabelWithInfo({ label, info }: { label: string; info: ReactNode }) {
  return (
    <span className="flex w-fit items-center gap-1.5">
      {label}
      <FieldInfoTooltip label={label}>{info}</FieldInfoTooltip>
    </span>
  );
}

function SshConfigAliasField({
  hosts,
  hostsByAlias,
  loadError,
  onSelectHost,
  onSelectManual,
}: {
  hosts: SshConfigHost[];
  hostsByAlias: Map<string, SshConfigHost>;
  loadError: string | null;
  onSelectHost: (host: SshConfigHost) => void;
  onSelectManual: () => void;
}) {
  const field = useFieldContext<string>();
  const selectedHost = hostsByAlias.get(field.state.value);
  const options = [
    { value: MANUAL_CONNECTION_VALUE, label: 'Manual connection' },
    ...hosts.map((host) => ({ value: host.host, label: host.host })),
  ];

  return (
    <FormFieldShell
      label={
        <FieldLabelWithInfo
          label="SSH Config"
          info="Select an entry from ~/.ssh/config to prefill host, user, key, proxy, and agent forwarding settings."
        />
      }
      description={loadError}
    >
      {({ id }) =>
        hosts.length > 0 ? (
          <ComboboxPopover
            items={options}
            value={field.state.value || MANUAL_CONNECTION_VALUE}
            onValueChange={(value) => {
              if (value === MANUAL_CONNECTION_VALUE) {
                onSelectManual();
                field.handleChange('');
                return;
              }

              const host = hostsByAlias.get(value);
              if (host) onSelectHost(host);
            }}
            itemToKey={(item) => item.value}
            itemToLabel={(item) => item.label}
            filter={(item, query) => item.label.toLowerCase().includes(query.toLowerCase())}
            appearance="input"
            className="w-full"
            contentWidth="trigger"
            searchPlaceholder="Search SSH config..."
            renderTrigger={() => (
              <span className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
                {selectedHost ? (
                  <span className="truncate">{selectedHost.host}</span>
                ) : field.state.value ? (
                  <span className="truncate">{field.state.value}</span>
                ) : (
                  'Manual connection'
                )}
              </span>
            )}
            renderItem={(item) => <span className="truncate">{item.label}</span>}
            triggerId={id}
          />
        ) : (
          <input id={id} name={field.name} value={field.state.value} type="hidden" readOnly />
        )
      }
    </FormFieldShell>
  );
}

export interface UseMachineFormOptions {
  initialConfig?: SshConfig;
  onSaved: (connectionId: string) => void;
}

export function useMachineForm({ initialConfig, onSaved }: UseMachineFormOptions) {
  const machines = getMachinesStore();
  const isEditing = !!initialConfig;
  const [testState, setTestState] = useState<TestState>('idle');
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [showDebugLogs, setShowDebugLogs] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(
    !!initialConfig?.proxyJump || initialConfig?.forwardAgent === true
  );
  const [selectedSshConfigAlias, setSelectedSshConfigAlias] = useState(
    initialConfig?.sshConfigAlias ?? ''
  );

  const findDuplicateMachine = useCallback(
    (name: string) =>
      machines.connections.find(
        (connection) =>
          connection.name === name && (!initialConfig || connection.id !== initialConfig.id)
      ),
    [initialConfig, machines]
  );

  const form = useAppForm({
    defaultValues: {
      name: initialConfig?.name ?? '',
      host: initialConfig?.host ?? '',
      port: initialConfig?.port ?? 22,
      username: initialConfig?.username ?? '',
      authType: (initialConfig?.authType ?? 'password') as MachineAuthType,
      password: '',
      privateKeyPath: initialConfig?.privateKeyPath ?? '',
      passphrase: '',
      sshConfigAlias: initialConfig?.sshConfigAlias ?? '',
      forwardAgent: initialConfig?.forwardAgent ?? false,
      proxyJump: initialConfig?.proxyJump ?? '',
      proxyCommand: '',
      isEditing,
    },
    validators: {
      onSubmit: machineFormSchema,
    },
    onSubmit: async ({ value }) => {
      setIsSubmitting(true);
      try {
        if (findDuplicateMachine(value.name)) {
          setTestState('idle');
          setTestResult(null);
          return;
        }

        const isAliasBacked = value.sshConfigAlias.trim().length > 0;
        const proxyJump = value.proxyJump.trim();
        const username = value.username || value.sshConfigAlias || value.host;
        const privateKeyPath = value.privateKeyPath.trim();
        const config: Partial<Pick<SshConfig, 'id'>> &
          Omit<SshConfig, 'id'> & { password?: string; passphrase?: string } = {
          id: initialConfig?.id,
          name: value.name,
          host: value.host,
          port: value.port,
          username,
          sshConfigAlias: value.sshConfigAlias || undefined,
          authType: value.authType,
          privateKeyPath:
            value.authType === 'key' && !isAliasBacked ? privateKeyPath || undefined : undefined,
          useAgent: value.authType === 'agent',
          forwardAgent: isAliasBacked ? undefined : value.forwardAgent,
          proxyJump: isAliasBacked ? undefined : proxyJump,
          password: value.authType === 'password' ? value.password : undefined,
          passphrase: value.authType === 'key' ? value.passphrase : undefined,
        };
        const saved = await machines.saveConnection(config);
        onSaved(saved.id);
      } catch (error) {
        setTestState('error');
        setTestResult({ success: false, error: formatMachineError(error) });
      } finally {
        setIsSubmitting(false);
      }
    },
  });

  const buildTestConfig = (): SshConfig & { password?: string; passphrase?: string } => {
    const value = form.state.values;
    const username = value.username || value.sshConfigAlias || value.host;
    const privateKeyPath = value.privateKeyPath.trim();
    return {
      id: '',
      name: value.name,
      host: value.host,
      port: value.port,
      username,
      sshConfigAlias: value.sshConfigAlias || undefined,
      authType: value.authType,
      privateKeyPath:
        value.authType === 'key' && !value.sshConfigAlias ? privateKeyPath || undefined : undefined,
      useAgent: value.authType === 'agent',
      forwardAgent: value.sshConfigAlias ? undefined : value.forwardAgent,
      proxyJump: value.sshConfigAlias ? undefined : value.proxyJump.trim() || undefined,
      password: value.authType === 'password' ? value.password : undefined,
      passphrase: value.authType === 'key' ? value.passphrase : undefined,
    };
  };

  const validateConnectionForm = async (): Promise<boolean> => {
    await form.validateAllFields('submit');
    await form.validate('submit');
    return form.state.isValid;
  };

  const sshConfigHostsQuery = useSshConfigHosts();
  const resolvedSshConfigHostQuery = useSshConfigHost(selectedSshConfigAlias);
  const sshConfigHosts = sshConfigHostsQuery.data ?? EMPTY_SSH_CONFIG_HOSTS;
  const sshConfigLoadError = sshConfigHostsQuery.error
    ? sshConfigHostsQuery.error instanceof Error
      ? sshConfigHostsQuery.error.message
      : String(sshConfigHostsQuery.error)
    : null;
  const sshConfigHostsByAlias = useMemo(
    () => new Map(sshConfigHosts.map((host) => [host.host, host])),
    [sshConfigHosts]
  );
  const selectedSshConfigHost =
    resolvedSshConfigHostQuery.data ?? sshConfigHostsByAlias.get(selectedSshConfigAlias);

  const applySshConfigHostFields = useCallback(
    (host: SshConfigHost) => {
      form.setFieldValue('host', host.hostname || host.host);
      form.setFieldValue('port', host.port ?? 22);
      form.setFieldValue('username', host.user ?? form.state.values.username);
      form.setFieldValue('authType', suggestedAuthTypeForSshConfigHost(host));
      form.setFieldValue('privateKeyPath', host.identityFile ?? form.state.values.privateKeyPath);
      form.setFieldValue('forwardAgent', host.forwardAgent ?? false);
      form.setFieldValue('proxyJump', host.proxyJump ?? '');
      form.setFieldValue('proxyCommand', host.proxyCommand ?? '');
    },
    [form]
  );

  useEffect(() => {
    if (!selectedSshConfigAlias || !selectedSshConfigHost) return;
    if (form.state.values.sshConfigAlias !== selectedSshConfigAlias) return;
    applySshConfigHostFields(selectedSshConfigHost);
  }, [applySshConfigHostFields, form, selectedSshConfigAlias, selectedSshConfigHost]);

  const applySshConfigHost = (host: SshConfigHost) => {
    setSelectedSshConfigAlias(host.host);
    form.setFieldValue('sshConfigAlias', host.host);
    form.setFieldValue('name', form.state.values.name || host.host);
    applySshConfigHostFields(host);
    setIsAdvancedOpen(true);
  };

  const selectManualConnection = () => {
    setSelectedSshConfigAlias('');
    form.setFieldValue('sshConfigAlias', '');
    form.setFieldValue('name', '');
    form.setFieldValue('host', '');
    form.setFieldValue('port', 22);
    form.setFieldValue('username', '');
    form.setFieldValue('authType', 'password');
    form.setFieldValue('privateKeyPath', '');
    form.setFieldValue('passphrase', '');
    form.setFieldValue('forwardAgent', false);
    form.setFieldValue('proxyJump', '');
    form.setFieldValue('proxyCommand', '');
    setIsAdvancedOpen(false);
  };

  const handleTestConnection = async () => {
    setTestResult(null);
    setShowDebugLogs(false);
    const isValid = await validateConnectionForm();
    if (!isValid) {
      setTestState('idle');
      return;
    }

    setTestState('testing');
    try {
      const result = await machines.testConnection(buildTestConfig());
      setTestResult(result);
      setTestState(result.success ? 'success' : 'error');
    } catch (error) {
      setTestState('error');
      setTestResult({ success: false, error: formatMachineError(error) });
    }
  };

  return {
    form,
    isEditing,
    isSubmitting,
    isAdvancedOpen,
    setIsAdvancedOpen,
    testState,
    testResult,
    showDebugLogs,
    setShowDebugLogs,
    sshConfigHosts,
    sshConfigHostsByAlias,
    sshConfigLoadError,
    shouldShowSshConfigField:
      sshConfigHosts.length > 0 || !!selectedSshConfigAlias || !!sshConfigLoadError,
    findDuplicateMachine,
    applySshConfigHost,
    selectManualConnection,
    handleTestConnection,
  };
}

export type MachineFormController = ReturnType<typeof useMachineForm>;

export function MachineFormFields({
  controller,
  formId,
}: {
  controller: MachineFormController;
  formId: string;
}) {
  const {
    form,
    isEditing,
    isAdvancedOpen,
    setIsAdvancedOpen,
    testState,
    testResult,
    showDebugLogs,
    setShowDebugLogs,
    sshConfigHosts,
    sshConfigHostsByAlias,
    sshConfigLoadError,
    shouldShowSshConfigField,
    findDuplicateMachine,
    applySshConfigHost,
    selectManualConnection,
  } = controller;

  return (
    <Tooltip.Provider delay={150}>
      <form
        id={formId}
        onSubmit={(event) => {
          event.preventDefault();
          void form.handleSubmit();
        }}
      >
        <div className="grid gap-3">
          <form.AppField name="name">
            {(field) => {
              const isDuplicate = !!findDuplicateMachine(field.state.value);
              return (
                <>
                  <field.TextField
                    label="Connection Name"
                    placeholder="My Server"
                    aria-invalid={isDuplicate || undefined}
                  />
                  {isDuplicate && (
                    <p role="alert" className="text-sm text-foreground-destructive">
                      {DUPLICATE_CONNECTION_NAME_ERROR}
                    </p>
                  )}
                </>
              );
            }}
          </form.AppField>

          {shouldShowSshConfigField && (
            <form.AppField name="sshConfigAlias">
              {() => (
                <SshConfigAliasField
                  hosts={sshConfigHosts}
                  hostsByAlias={sshConfigHostsByAlias}
                  loadError={sshConfigLoadError}
                  onSelectHost={applySshConfigHost}
                  onSelectManual={selectManualConnection}
                />
              )}
            </form.AppField>
          )}

          <form.Subscribe selector={(state) => state.values.sshConfigAlias}>
            {(sshConfigAlias) => {
              const isAliasBacked = !!sshConfigAlias;
              return (
                <>
                  <div className="grid grid-cols-[1fr_6rem] gap-3">
                    <form.AppField name="host">
                      {(field) => (
                        <field.TextField
                          label="Host"
                          placeholder="203.0.113.10"
                          disabled={isAliasBacked}
                        />
                      )}
                    </form.AppField>
                    <form.AppField name="port">
                      {(field) => <field.NumberField label="Port" disabled={isAliasBacked} />}
                    </form.AppField>
                  </div>

                  <form.AppField name="username">
                    {(field) => (
                      <field.TextField
                        label="Username"
                        placeholder="ubuntu"
                        autoComplete="off"
                        disabled={isAliasBacked}
                      />
                    )}
                  </form.AppField>
                </>
              );
            }}
          </form.Subscribe>

          <form.AppField name="authType">
            {(field) => (
              <field.RadioGroupField
                label={
                  <FieldLabelWithInfo
                    label="Authentication"
                    info="Choose how Hardcore authenticates to the remote server. SSH config entries can preselect the best option."
                  />
                }
                layout="row"
                options={[
                  { value: 'password', label: 'Password' },
                  { value: 'key', label: 'SSH Key' },
                  { value: 'agent', label: 'Agent' },
                ]}
              />
            )}
          </form.AppField>

          <form.Subscribe
            selector={(state) => ({
              authType: state.values.authType,
              sshConfigAlias: state.values.sshConfigAlias,
            })}
          >
            {({ authType, sshConfigAlias }) => {
              if (authType === 'password') {
                return (
                  <form.AppField name="password">
                    {(field) => (
                      <field.TextField
                        label="Password"
                        type="password"
                        autoComplete="current-password"
                        placeholder={isEditing ? 'Leave blank to keep existing' : undefined}
                      />
                    )}
                  </form.AppField>
                );
              }

              if (authType === 'key') {
                return (
                  <>
                    <form.AppField name="privateKeyPath">
                      {(field) => (
                        <field.TextField
                          label={
                            <FieldLabelWithInfo
                              label="Private Key Path"
                              info="Path on this machine to the private key used for the connection, for example ~/.ssh/id_ed25519."
                            />
                          }
                          placeholder="~/.ssh/id_rsa"
                          disabled={!!sshConfigAlias}
                        />
                      )}
                    </form.AppField>
                    <form.AppField name="passphrase">
                      {(field) => (
                        <field.TextField
                          label={
                            <FieldLabelWithInfo
                              label="Passphrase"
                              info="Only needed if the selected private key is encrypted with a passphrase."
                            />
                          }
                          type="password"
                          placeholder={isEditing ? 'Leave blank to keep existing' : 'Optional'}
                          autoComplete="off"
                          description={
                            !isEditing ? 'Leave empty if your key has no passphrase.' : undefined
                          }
                        />
                      )}
                    </form.AppField>
                  </>
                );
              }

              return (
                <p className="text-sm text-foreground-muted">
                  The SSH agent running on this machine will be used for authentication. Make sure
                  your key is loaded into the agent.
                </p>
              );
            }}
          </form.Subscribe>

          <form.Subscribe
            selector={(state) => ({
              sshConfigAlias: state.values.sshConfigAlias,
              proxyCommand: state.values.proxyCommand,
            })}
          >
            {({ sshConfigAlias, proxyCommand }) => {
              const isAliasBacked = !!sshConfigAlias;
              const showProxyCommand = isAliasBacked && proxyCommand.trim().length > 0;

              return (
                <Collapsible.Root
                  open={isAliasBacked || isAdvancedOpen}
                  onOpenChange={isAliasBacked ? undefined : setIsAdvancedOpen}
                >
                  <Collapsible.Trigger type="button" disabled={isAliasBacked}>
                    Advanced
                  </Collapsible.Trigger>
                  <Collapsible.Panel className="grid gap-3 pt-2">
                    {showProxyCommand ? (
                      <form.AppField name="proxyCommand">
                        {(field) => (
                          <field.TextField
                            label={
                              <FieldLabelWithInfo
                                label="ProxyCommand"
                                info="Command from your SSH config used to reach this host through a proxy. It is read-only here because it comes from ~/.ssh/config."
                              />
                            }
                            disabled
                          />
                        )}
                      </form.AppField>
                    ) : (
                      <form.AppField name="proxyJump">
                        {(field) => (
                          <field.TextField
                            label={
                              <FieldLabelWithInfo
                                label="ProxyJump"
                                info="Optional bastion host to connect through before reaching the target server, for example user@bastion:2222."
                              />
                            }
                            placeholder="bastion or user@bastion:2222"
                            autoComplete="off"
                            disabled={isAliasBacked}
                          />
                        )}
                      </form.AppField>
                    )}

                    <form.AppField name="forwardAgent">
                      {(field) => (
                        <field.SwitchField
                          label={
                            <FieldLabelWithInfo
                              label="ForwardAgent"
                              info="Forward your local SSH agent to the remote server so nested SSH and Git commands can use your loaded local keys. Enable only for trusted hosts."
                            />
                          }
                          disabled={isAliasBacked}
                          className="rounded-md border border-border px-3 py-2"
                        />
                      )}
                    </form.AppField>
                  </Collapsible.Panel>
                </Collapsible.Root>
              );
            }}
          </form.Subscribe>
        </div>
      </form>

      {testState !== 'idle' && (
        <div className="rounded-md border border-border px-3 py-2 text-sm">
          <div className="flex items-center gap-2">
            {testState === 'testing' && (
              <LoaderCircle className="size-4 animate-spin text-foreground-muted" />
            )}
            {testState === 'success' && <CheckCircle2 className="size-4 text-foreground-success" />}
            {testState === 'error' && <XCircle className="size-4 text-foreground-destructive" />}
            <span className="flex-1 font-medium">
              {testState === 'testing' && 'Testing connection…'}
              {testState === 'success' &&
                `Connected${testResult?.latency ? ` (${testResult.latency}ms)` : ''}`}
              {testState === 'error' && (testResult?.error ?? 'Connection failed')}
            </span>
            {testState === 'error' && testResult?.debugLogs?.length ? (
              <button
                type="button"
                onClick={() => setShowDebugLogs((value) => !value)}
                className="flex items-center gap-1 text-xs text-foreground-muted hover:text-foreground"
              >
                {showDebugLogs ? (
                  <ChevronUp className="size-3" />
                ) : (
                  <ChevronDown className="size-3" />
                )}
                Logs
              </button>
            ) : null}
          </div>
          {showDebugLogs && testResult?.debugLogs && (
            <pre className="mt-2 max-h-32 overflow-y-auto rounded bg-background-2 px-2 py-1.5 text-xs text-foreground-muted">
              {testResult.debugLogs.join('\n')}
            </pre>
          )}
        </div>
      )}
    </Tooltip.Provider>
  );
}

export function MachineFormActions({
  controller,
  formId,
  leadingAction,
  cancelAction,
}: {
  controller: MachineFormController;
  formId: string;
  leadingAction?: ReactNode;
  cancelAction?: ReactNode;
}) {
  const { form, isSubmitting, testState, findDuplicateMachine, handleTestConnection } = controller;

  return (
    <div className="flex w-full items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {leadingAction}
        <Button
          type="button"
          variant="secondary"
          onClick={() => void handleTestConnection()}
          disabled={testState === 'testing'}
        >
          {testState === 'testing' ? (
            <>
              <LoaderCircle className="size-4 animate-spin" />
              Testing…
            </>
          ) : (
            'Test Connection'
          )}
        </Button>
      </div>

      <div className="flex items-center gap-2">
        {cancelAction}
        <form.Subscribe
          selector={(state) => ({
            canSubmit: state.canSubmit,
            name: state.values.name,
          })}
        >
          {({ canSubmit, name }) => (
            <form.AppForm>
              <form.SubmitButton
                form={formId}
                disabled={isSubmitting || !canSubmit || !!findDuplicateMachine(name)}
              >
                {isSubmitting ? (
                  <>
                    <LoaderCircle className="size-4 animate-spin" />
                    Saving…
                  </>
                ) : (
                  'Save'
                )}
              </form.SubmitButton>
            </form.AppForm>
          )}
        </form.Subscribe>
      </div>
    </div>
  );
}

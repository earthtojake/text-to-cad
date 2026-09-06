import { readFile } from 'node:fs/promises';
import os from 'node:os';
import type { Logger } from '@emdash/shared/logger';
import type { PluginRegistry } from '@emdash/shared/plugins';
import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { acpApiContract } from '#runtimes/acp/api';
import { createAcpController } from '#runtimes/acp/node/api/controller';
import { ChildAcpProcessHost } from '#runtimes/acp/node/node/child-process-host';
import { LocalAttachmentStore } from '#runtimes/acp/node/node/local-attachment-store';
import { AcpRuntime } from '#runtimes/acp/node/runtime/runtime';
import type { AcpRuntimeDeps } from '#runtimes/acp/node/runtime/types';
import { AgentPluginHost, type CLIAgentPluginProvider } from '#services/agent-plugins/api/plugins';
import { createLocalPluginFs } from '#services/agent-plugins/api/plugins/helpers';
import { conversationReportsContract } from '#services/conversation-reports/api';
import { createConversationLifecycleReporter } from '#services/conversation-reports/node';
import { NodeExecutionContext } from '#services/exec/api';
import {
  createHostDependencyResolverFromDependency,
  hostDependencyResolverContract,
} from '#services/host-dependencies/node';
import {
  createFileSessionIntentStore,
  createNoopSessionIntentStore,
} from '#services/session-intents/node';
import { idlePolicyConfigSchema } from '#services/session-lifecycle/api';
import { userShellEnvContract } from '#services/shell-env/api';

export const acpComponentConfigSchema = z.object({
  attachmentsDir: z.string().min(1),
  intentsFilePath: z.string().min(1).optional(),
  lifecycle: z
    .object({
      session: idlePolicyConfigSchema.optional(),
      sweepIntervalMs: z.number().int().positive().optional(),
      connectionIdleTtlMs: z.number().int().positive().optional(),
    })
    .optional(),
});

export type CreateAcpComponentOptions = {
  pluginRegistry: PluginRegistry<CLIAgentPluginProvider>;
  logger?: Logger;
};

export function createAcpComponent(options: CreateAcpComponentOptions) {
  return defineWireComponent({
    id: 'acp',
    contract: acpApiContract,
    requirements: {
      hostDependencies: requireContract(hostDependencyResolverContract),
      conversations: requireContract(conversationReportsContract),
      userEnv: requireContract(userShellEnvContract),
    },
    configSchema: acpComponentConfigSchema,
    create: ({ config, dependencies, instance, logger, scope }) => {
      const env = () => dependencies.userEnv.get();
      const runtimeLogger = options.logger ?? logger;
      const childHost = new ChildAcpProcessHost();
      const attachmentStore = new LocalAttachmentStore(config.attachmentsDir);
      const homeDir = os.homedir();
      const exec = new NodeExecutionContext({ env });
      const dependencyResolver = createHostDependencyResolverFromDependency(
        dependencies.hostDependencies
      );
      const intents = config.intentsFilePath
        ? createFileSessionIntentStore({ path: config.intentsFilePath, scope: 'acp' })
        : createNoopSessionIntentStore();
      const agentHost = new AgentPluginHost({
        scope,
        registry: options.pluginRegistry,
        exec,
        dependencies: dependencyResolver,
        fs: createLocalPluginFs(homeDir),
        env,
        homeDir,
      });
      const acp = new AcpRuntime({
        agentHost,
        host: childHost,
        resolveAttachment: async (conversationId, attachment) => {
          if (attachment.type === 'attachment') {
            const stored = await attachmentStore.get(conversationId, attachment.id);
            if (!stored) throw new Error(`Attachment '${attachment.id}' could not be resolved`);
            return {
              data: Buffer.from(stored.data).toString('base64'),
              mimeType: stored.ref.mimeType,
            };
          }
          const data = await readFile(attachment.originalPath);
          return {
            data: data.toString('base64'),
            mimeType: attachment.mimeType,
          };
        },
        attachmentStore,
        intents,
        conversationReports: createConversationLifecycleReporter({
          client: dependencies.conversations,
          logger: runtimeLogger,
        }),
        lifecycle: config.lifecycle,
        logger: runtimeLogger,
      } satisfies AcpRuntimeDeps);
      void acp.reconcile();

      scope.add(() => acp.dispose());
      return instance({
        scope,
        controller: createAcpController(acp),
      });
    },
  });
}

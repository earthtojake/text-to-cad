import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { z } from 'zod';
import { taskSubject } from '@core/features/tasks/contributions/subject';
import { defineMemento } from '@core/primitives/mementos/api';

export const cadRunStatusSchema = z.enum([
  'ready',
  'generating',
  'validating',
  'completed',
  'failed',
  'cancelled',
  'interrupted',
  'restored',
]);

export const cadModelConversationTypeSchema = z.enum([
  'design',
  'analysis',
  'manufacturing',
  'review',
  'custom',
]);

const cadArtifactSchema = z.object({
  path: z.string(),
  role: z.enum(['model', 'source']),
});

const cadRunSchema = z.object({
  id: z.string().optional(),
  conversationId: z.string().optional(),
  origin: z.enum(['agent', 'source']).optional(),
  status: cadRunStatusSchema,
  prompt: z.string().optional(),
  startedAt: z.string().optional(),
  endedAt: z.string().optional(),
  validation: z
    .object({
      status: z.enum(['passed', 'failed']),
      checkedAt: z.string(),
      error: z.string().optional(),
      facts: z
        .object({
          occurrenceCount: z.number().optional(),
          faceCount: z.number().optional(),
          size: z.tuple([z.number(), z.number(), z.number()]).optional(),
        })
        .optional(),
    })
    .optional(),
});

const cadLastGoodSchema = z.object({
  modelPath: z.string(),
  backupPath: z.string().optional(),
  /** The `<model>.step.json` declarations sidecar, when the accepted STEP had one. */
  sidecarPath: z.string().optional(),
  sidecarBackupPath: z.string().optional(),
  sourcePath: z.string().optional(),
  sourceBackupPath: z.string().optional(),
  recordedAt: z.string(),
  validationStatus: z.enum(['passed', 'unknown']),
  revisionId: z.string().optional(),
  modelHash: z.string().optional(),
  sourceHash: z.string().optional(),
});

const cadModelRecordV1Schema = z.object({
  contextKey: z.string(),
  modelPath: z.string(),
  sourcePath: z.string().optional(),
  conversationId: z.string().optional(),
  artifacts: z.array(cadArtifactSchema),
  run: cadRunSchema,
  lastGood: cadLastGoodSchema.optional(),
  updatedAt: z.string(),
});

export const cadModelConversationSchema = z.object({
  id: z.string(),
  type: cadModelConversationTypeSchema,
  createdAt: z.string(),
  updatedAt: z.string(),
  /** UI-only soft archive. The conversation transcript and every model artifact remain intact. */
  archivedAt: z.string().optional(),
  lastContextRevisionId: z.string().optional(),
  /** Frozen wall-clock durations keyed by stable transcript turn id. */
  turnDurationsMs: z.record(z.string(), z.number().nonnegative()).optional(),
});

export const cadModelRecordSchema = z.object({
  contextKey: z.string(),
  modelPath: z.string(),
  sourcePath: z.string().optional(),
  artifacts: z.array(cadArtifactSchema),
  conversations: z.record(z.string(), cadModelConversationSchema),
  activeConversationId: z.string().optional(),
  editingConversationId: z.string().optional(),
  revisionId: z.string().optional(),
  modelHash: z.string().optional(),
  sourceHash: z.string().optional(),
  run: cadRunSchema,
  lastGood: cadLastGoodSchema.optional(),
  updatedAt: z.string(),
});

const cadModelCatalogV1Schema = z.object({
  version: z.literal('1'),
  activeModelKey: z.string().optional(),
  models: z.record(z.string(), cadModelRecordV1Schema),
});

const cadModelCatalogV2Schema = z.object({
  version: z.literal('2'),
  activeModelKey: z.string().optional(),
  models: z.record(z.string(), cadModelRecordSchema),
});

const cadModelCatalogV3Schema = z.object({
  version: z.literal('3'),
  activeModelKey: z.string().optional(),
  models: z.record(z.string(), cadModelRecordSchema),
});

export const cadModelCatalogSchema = defineVersionedSchema()
  .initial('1', cadModelCatalogV1Schema)
  .version('2', cadModelCatalogV2Schema, (catalog) => ({
    version: '2' as const,
    ...(catalog.activeModelKey ? { activeModelKey: catalog.activeModelKey } : {}),
    models: Object.fromEntries(
      Object.entries(catalog.models).map(([contextKey, model]) => {
        const conversationId = model.conversationId;
        const conversations = conversationId
          ? {
              [conversationId]: {
                id: conversationId,
                type: 'design' as const,
                createdAt: model.updatedAt,
                updatedAt: model.updatedAt,
                ...(model.run.status === 'completed' && model.run.id
                  ? { lastContextRevisionId: model.run.id }
                  : {}),
              },
            }
          : {};
        const revisionId =
          model.run.status === 'completed' && model.run.validation?.status === 'passed'
            ? model.run.id
            : model.lastGood?.validationStatus === 'passed'
              ? `legacy:${model.lastGood.recordedAt}`
              : undefined;
        return [
          contextKey,
          {
            contextKey: model.contextKey,
            modelPath: model.modelPath,
            ...(model.sourcePath ? { sourcePath: model.sourcePath } : {}),
            artifacts: model.artifacts,
            conversations,
            ...(conversationId ? { activeConversationId: conversationId } : {}),
            ...(conversationId ? { editingConversationId: conversationId } : {}),
            ...(revisionId ? { revisionId } : {}),
            run: model.run,
            ...(model.lastGood
              ? {
                  lastGood: {
                    ...model.lastGood,
                    ...(revisionId ? { revisionId } : {}),
                  },
                }
              : {}),
            updatedAt: model.updatedAt,
          },
        ];
      })
    ),
  }))
  .version('3', cadModelCatalogV3Schema, (catalog) => ({
    ...catalog,
    version: '3' as const,
  }))
  .build();

export type CadModelCatalog = typeof cadModelCatalogSchema.Type;
export type CadModelRecord = z.infer<typeof cadModelRecordSchema>;
export type CadModelConversation = z.infer<typeof cadModelConversationSchema>;
export type CadModelConversationType = z.infer<typeof cadModelConversationTypeSchema>;
export type CadRunStatus = z.infer<typeof cadRunStatusSchema>;

export const cadModelCatalogMemento = defineMemento({
  id: 'cad.model-catalog',
  subject: taskSubject,
  schema: cadModelCatalogSchema,
  default: {
    version: '3' as const,
    models: {},
  },
});

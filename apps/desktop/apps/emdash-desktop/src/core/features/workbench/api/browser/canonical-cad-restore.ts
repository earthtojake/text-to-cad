import type { CadModelCatalog, CadModelRecord } from '@core/features/cad/contributions/mementos';
import type { Conversation } from '@core/primitives/conversations/api';

export interface CanonicalCadRestorePlan {
  contextKey: string;
  path: string;
  conversationId?: string;
}

export interface LegacyCadRestorePlan {
  contextKey: string;
  conversationId: string;
  candidatePaths: readonly string[];
}

export interface PersistedCadTab {
  tabId: string;
  path: string;
  contextKey: string;
}

export interface CanonicalCadTabRetargetPlan {
  tabId: string;
  path: string;
}

/**
 * Retargets every persisted recipe tab from the task catalog, not only the
 * currently active model. Explicit source/model links are authoritative so a
 * recipe may live in a different directory or use a different stem from the
 * STEP it produces.
 */
export function planCanonicalCadCatalogTabRetargets(
  catalog: CadModelCatalog,
  tabs: readonly PersistedCadTab[]
): CanonicalCadTabRetargetPlan[] {
  const models = Object.values(catalog.models);
  return tabs.flatMap((tab) => {
    const tabPath = normalizePath(tab.path);
    if (models.some((model) => normalizePath(model.modelPath) === tabPath)) return [];

    const explicitSourceMatches = models.filter(
      (model) => model.sourcePath && normalizePath(model.sourcePath) === tabPath
    );
    const contextMatch = tabPath.toLowerCase().endsWith('.py')
      ? models.find((model) => model.contextKey === tab.contextKey)
      : undefined;
    const model =
      explicitSourceMatches.length === 1
        ? explicitSourceMatches[0]
        : explicitSourceMatches.length > 1
          ? explicitSourceMatches.find((candidate) => candidate.contextKey === tab.contextKey)
          : contextMatch;
    return model ? [{ tabId: tab.tabId, path: model.modelPath }] : [];
  });
}

export function planCanonicalCadTabRetarget(
  restorePlan: CanonicalCadRestorePlan,
  tabs: readonly PersistedCadTab[]
): CanonicalCadTabRetargetPlan | null {
  return planCanonicalCadTabRetargets(restorePlan, tabs)[0] ?? null;
}

export function planCanonicalCadTabRetargets(
  restorePlan: CanonicalCadRestorePlan,
  tabs: readonly PersistedCadTab[]
): CanonicalCadTabRetargetPlan[] {
  return tabs.flatMap((tab) =>
    tab.contextKey === restorePlan.contextKey &&
    normalizePath(tab.path) !== normalizePath(restorePlan.path)
      ? [{ tabId: tab.tabId, path: restorePlan.path }]
      : []
  );
}

/**
 * Recovers the CAD focus for an existing task when its pane layout is empty or
 * incomplete. The task-scoped CAD catalog is authoritative; filename guessing
 * would be ambiguous in projects that contain several models.
 */
export function planCanonicalCadRestore(
  catalog: CadModelCatalog,
  conversations: readonly Conversation[]
): CanonicalCadRestorePlan | null {
  const model = selectRestoreModel(catalog, conversations);
  if (!model) return null;

  const conversationId = selectRestoreConversation(model, conversations)?.id;
  return {
    contextKey: model.contextKey,
    // Restore only the accepted artifact. The linked source remains catalog
    // context for Source/History, but opening a task must never execute it or
    // let stale recipe bytes overwrite the canonical STEP.
    path: model.modelPath,
    ...(conversationId ? { conversationId } : {}),
  };
}

/**
 * Older model chats can predate the CAD catalog. Their stable CAD context key
 * still gives us a bounded set of same-stem files to check without scanning or
 * guessing from the task title.
 */
export function planLegacyCadRestore(
  conversations: readonly Conversation[]
): LegacyCadRestorePlan | null {
  const conversation = newestConversation(
    conversations.filter(
      (candidate) =>
        candidate.type === 'acp' && candidate.contextKey?.startsWith('cad-model:') === true
    )
  );
  if (!conversation?.contextKey) return null;

  const stem = safeRelativeCadStem(conversation.contextKey.slice('cad-model:'.length));
  if (!stem) return null;
  return {
    contextKey: conversation.contextKey,
    conversationId: conversation.id,
    candidatePaths: [
      `${stem}.step`,
      `${stem}.stp`,
      `${stem}.stl`,
      `${stem}.3mf`,
      `${stem}.glb`,
      `${stem}.dxf`,
    ],
  };
}

function selectRestoreModel(
  catalog: CadModelCatalog,
  conversations: readonly Conversation[]
): CadModelRecord | null {
  if (catalog.activeModelKey) {
    const active = catalog.models[catalog.activeModelKey];
    if (active) return active;
  }

  const conversationContextKeys = new Set(
    conversations.flatMap((conversation) =>
      conversation.contextKey?.startsWith('cad-model:') ? [conversation.contextKey] : []
    )
  );
  const models = Object.values(catalog.models);
  const matchingModels = models.filter((model) => conversationContextKeys.has(model.contextKey));
  if (matchingModels.length > 0) return newestModel(matchingModels);
  return models.length === 1 ? models[0]! : null;
}

function selectRestoreConversation(
  model: CadModelRecord,
  conversations: readonly Conversation[]
): Conversation | undefined {
  const availableConversations = conversations.filter(
    (conversation) => !model.conversations[conversation.id]?.archivedAt
  );
  const active = availableConversations.find(
    (conversation) => conversation.id === model.activeConversationId
  );
  if (active) return active;

  const modelConversations = availableConversations.filter(
    (conversation) => conversation.contextKey === model.contextKey
  );
  const initialModelConversation = modelConversations.find(
    (conversation) => conversation.isInitialConversation === true
  );
  if (initialModelConversation) return initialModelConversation;
  if (modelConversations.length > 0) return newestConversation(modelConversations);

  return (
    availableConversations.find((conversation) => conversation.isInitialConversation === true) ??
    newestConversation(availableConversations)
  );
}

function newestModel(models: readonly CadModelRecord[]): CadModelRecord | null {
  return (
    [...models].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0] ?? null
  );
}

function newestConversation(conversations: readonly Conversation[]): Conversation | undefined {
  return [...conversations].sort(
    (left, right) => timestamp(right.lastInteractedAt) - timestamp(left.lastInteractedAt)
  )[0];
}

function safeRelativeCadStem(value: string): string | null {
  const normalized = value.replaceAll('\\', '/').replace(/^\.\//, '');
  if (
    !normalized ||
    normalized.startsWith('/') ||
    /^[a-z]:\//i.test(normalized) ||
    normalized.split('/').some((segment) => !segment || segment === '..')
  ) {
    return null;
  }
  return normalized;
}

function timestamp(value: string | null): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function normalizePath(value: string): string {
  return value.replaceAll('\\', '/').replace(/^\.\//, '');
}

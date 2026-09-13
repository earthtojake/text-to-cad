import type { CadModelConversationType } from '@core/features/cad/contributions/mementos';
import type { Conversation } from '@core/primitives/conversations/api';

export function selectCadConversation(
  conversations: readonly Conversation[],
  contextKey: string,
  activeConversationIds: ReadonlySet<string>,
  preferredConversationId?: string
): Conversation | null {
  return selectContextConversation(
    conversations,
    contextKey,
    activeConversationIds,
    preferredConversationId
  );
}

export function cadConversationsForModel(
  conversations: readonly Conversation[],
  contextKey: string
): Conversation[] {
  return conversations.filter(
    (conversation) => conversation.type === 'acp' && conversation.contextKey === contextKey
  );
}

export function selectContextConversation(
  conversations: readonly Conversation[],
  contextKey: string,
  activeConversationIds: ReadonlySet<string>,
  preferredConversationId?: string
): Conversation | null {
  const candidates = cadConversationsForModel(conversations, contextKey);
  if (candidates.length === 0) return null;
  const preferred = candidates.find((conversation) => conversation.id === preferredConversationId);
  if (preferred) return preferred;

  return [...candidates].sort((left, right) => {
    const activeDifference =
      Number(activeConversationIds.has(right.id)) - Number(activeConversationIds.has(left.id));
    if (activeDifference !== 0) return activeDifference;
    const workingDifference =
      Number(right.agentStatus === 'working') - Number(left.agentStatus === 'working');
    if (workingDifference !== 0) return workingDifference;
    const initialDifference =
      Number(right.isInitialConversation === true) - Number(left.isInitialConversation === true);
    if (initialDifference !== 0) return initialDifference;
    return timestamp(right.lastInteractedAt) - timestamp(left.lastInteractedAt);
  })[0];
}

const CAD_SOURCE_SUFFIXES = [
  '.step.py',
  '.stp.py',
  '.implicit.mjs',
  '.implicit.js',
  '.py',
] as const;
const CAD_ARTIFACT_SUFFIXES = ['.step', '.stp', '.stl', '.3mf', '.glb', '.dxf'] as const;

/**
 * Hardcore shows models itself; an agent that follows the CAD skill's viewer
 * hand-off would otherwise start a second viewer server and post links to it.
 */
export function buildHardcoreViewerContext(): string {
  return [
    'Hardcore opens new CAD artifacts beside the chat as you build them. During longer CAD tasks, publish valid intermediate builds to the same output path at meaningful milestones so the viewer updates live.',
    'Follow the cad-desktop skill for viewing and hand-off. The cad-viewer skill is intentionally absent here: do not start a viewer server and do not post "Open in CAD Viewer" links; refer to files by their workspace-relative path and the viewer shows them.',
  ].join('\n');
}

export function buildCadFirstRoutingContext(): string {
  return [
    'Hardcore is a CAD-first engineering workspace with general agent tools available when they help.',
    'Unless the user explicitly asks for a bitmap image, illustration, or concept art, interpret requests to make, build, design, or model a physical object as CAD work.',
    'For CAD work, use the bundled Text-to-CAD skill and create or update the appropriate STEP-first engineering artifact in the current project.',
    'Do not choose image generation merely because a request describes an object, its appearance, or a scene.',
    'When a request asks to design or model a physical object, treat attached images as CAD references unless the user explicitly requests image output or image editing.',
    "For screenshots, diagrams, and documents, follow the user's stated task instead of forcing CAD.",
    'Web search, analysis, and other tools remain available when the engineering task calls for them.',
    buildHardcoreViewerContext(),
  ].join('\n');
}

export function cadModelContextKey(relativePath: string): string {
  const normalized = relativePath.replaceAll('\\', '/');
  const lowercase = normalized.toLowerCase();
  const suffix = [...CAD_SOURCE_SUFFIXES, ...CAD_ARTIFACT_SUFFIXES].find((candidate) =>
    lowercase.endsWith(candidate)
  );
  const stem = suffix ? normalized.slice(0, -suffix.length) : normalized;
  return `cad-model:${stem}`;
}

export function buildCadAgentContext(input: {
  relativePath: string;
  modelFiles: readonly string[];
  revisionId?: string | null;
  modelHash?: string | null;
  sourceHash?: string | null;
  conversationType: CadModelConversationType;
  canEditGeometry: boolean;
  projectBrief?: string | null;
  projectReferencePath?: string | null;
  manufacturingProfile?: string | null;
  engineeringWorkspace?: string | null;
  analysisRootPath?: string | null;
}): string {
  const context = [
    buildCadFirstRoutingContext(),
    "You are working from Hardcore's integrated CAD workspace.",
    `The current CAD target is: ${input.relativePath}`,
    `The current accepted artifact revision is: ${input.revisionId ?? 'not yet validated'}.`,
    'The artifact revision is the SHA-256 of the accepted on-disk STEP file.',
    `The current model file SHA-256 is: ${input.modelHash ?? 'not yet recorded'}.`,
    `The current generator source SHA-256 is: ${input.sourceHash ?? 'not present or not yet recorded'}.`,
    `The files currently associated with this focus are:\n${input.modelFiles.map((path) => `- ${path}`).join('\n')}`,
    `This chat currently has a ${input.conversationType} focus.`,
    'You may inspect and edit any relevant CAD model, drawing, assembly, analysis, or supporting file in this project when the user requests it.',
    'If the target is generated, follow the render package provenance to its @step Python source instead of guessing from filenames.',
    'Keep generated runtime caches out of source control.',
  ];
  if (input.canEditGeometry) {
    context.push(
      'This chat may change CAD geometry and other engineering artifacts.',
      'Implement geometry requests instead of only explaining them.',
      'Regenerate the artifact and run the CAD inspect/validate checks before finishing.'
    );
  } else {
    context.push(
      'This chat is temporarily read-only because its focused artifact is unavailable or already being revised.',
      'Discuss and review the current files until the active revision finishes.'
    );
  }
  if (input.conversationType === 'analysis' && input.analysisRootPath) {
    context.push(
      `Structured analysis artifacts for this model live at: ${input.analysisRootPath}`,
      'You may read and update analysis manifests and solver-native analysis files there without changing CAD geometry.'
    );
  }
  if (input.projectBrief) context.push(input.projectBrief);
  if (input.manufacturingProfile) context.push(input.manufacturingProfile);
  if (input.engineeringWorkspace) context.push(input.engineeringWorkspace);
  if (input.projectReferencePath) {
    context.push(
      `Project reference files are stored at: ${input.projectReferencePath}`,
      'Read relevant reference files before changing geometry when host permissions allow.'
    );
  }
  return context.join('\n');
}

function timestamp(value: string | null): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

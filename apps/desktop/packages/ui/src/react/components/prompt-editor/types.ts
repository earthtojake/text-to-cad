/**
 * Public types for the PromptEditor component.
 * Keep this file dependency-free (no TipTap imports) so consumers can type-check
 * without pulling the whole editor bundle.
 */

import type { ReactNode } from 'react';

// ── Mention items (@ trigger) ─────────────────────────────────────────────────

export type MentionKind = 'file' | 'issue' | 'symbol' | 'custom';

export interface MentionItem {
  /** Stable unique identifier (e.g. a file path or issue identifier). */
  id: string;
  /**
   * Serialization label — written as `@label` in clipboard / plain-text output.
   * Typically the full path for files.
   */
  label: string;
  /** Semantic category used for rendering (icon, chip colour, etc.). */
  kind: MentionKind;
  /**
   * Short display name shown inside the inline pill.
   * Defaults to the basename of `label` when not provided.
   */
  name?: string;
  /**
   * Exact serialized token to preserve for a controlled mention.
   * Omit for the canonical serialization derived from label, name, and kind.
   */
  serializedText?: string;
  /**
   * Optional icon rendered in the suggestion popup (not in the pill — the pill
   * derives its icon from `kind`/`label`). Pass a React element, e.g. a lucide icon.
   */
  icon?: ReactNode;
  /** Optional secondary description shown in the popup row. */
  description?: string;
  /** When provided, selecting this item inserts raw text instead of a mention node. */
  insertText?: string;
  /** Host-controlled resolving state for mention pills. Not included in plain-text serialization. */
  pending?: boolean;
}

export type RenderMentionIcon = (attrs: {
  id: string;
  label: string;
  kind: MentionKind;
}) => ReactNode | null;

// ── Context mention provider ──────────────────────────────────────────────────

/**
 * Injectable provider that the host application wires to supply @ mention
 * suggestions. Prefer this over the lower-level `queryMentions` callback when
 * building a typed feature — it is easier to extend (group metadata, async
 * cancel, etc.) without breaking the component API.
 */
export interface ContextMentionProvider {
  /** Return suggestions matching the given partial query string. */
  search(query: string): Promise<MentionItem[]>;
}

// ── Command items (/ trigger) ─────────────────────────────────────────────────

/**
 * 'insert' → insert a /token node into the doc.
 * 'insert-text' → insert raw text into the doc.
 * 'execute' → run a side-effect and clear the trigger.
 */
export type CommandBehavior = 'insert' | 'insert-text' | 'execute';

export interface CommandItem {
  id: string;
  /** Short display name (no leading slash). */
  name: string;
  /** Text displayed in the popup. Defaults to name if omitted. */
  label?: string;
  description?: string;
  behavior: CommandBehavior;
  /** Raw text inserted for behavior='insert-text'. */
  insertText?: string;
  /** Optional visual grouping label in the slash command popup. */
  section?: string;
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface PromptEditorRef {
  /** Focus the editor. */
  focus(): void;
  /** Clear all content. */
  clear(): void;
  /** Read the current serialized plain text. */
  getText(): string;
  /** Read the current selection as offsets into the serialized plain text. */
  getSelection(): { from: number; to: number };
  /** Resolve viewport coordinates to an offset in the serialized plain text. */
  getPositionAtCoordinates(coordinates: { left: number; top: number }): number | null;
  /** Replace the editor contents with serialized plain text. */
  setText(text: string): void;
  /** Imperatively insert a mention node at the current cursor position. */
  insertMention(item: MentionItem): void;
  /** Ensure a mention node exists at the start of the editor, replacing duplicates. */
  prependMention(item: MentionItem): void;
  /** Remove all mention nodes with the given id. */
  removeMention(id: string): void;
  /** Update the pending state for mention nodes with the given id. */
  setMentionPending(id: string, pending: boolean): void;
}

export type PromptSubmitShortcut = 'enter' | 'mod-enter' | 'none';

export interface PromptEditorProps {
  /**
   * Optional controlled serialized plain-text value.
   * Omit this prop to keep the editor internally managed.
   */
  value?: string;
  /** Controlled placeholder text when the editor is empty. */
  placeholder?: string;
  /** Whether the editor is disabled (read-only, no input). */
  disabled?: boolean;
  /** Called with the serialized plain-text value on every change. */
  onChange?: (text: string) => void;
  /** Keyboard shortcut that submits when no suggestion is open. Defaults to Enter. */
  submitShortcut?: PromptSubmitShortcut;
  /** Whether a successful submit clears the editor. Defaults to true. */
  clearOnSubmit?: boolean;
  /** Whether the submit callback runs for an empty document. Defaults to false. */
  allowEmptySubmit?: boolean;
  /** Called when the user submits with the configured shortcut. */
  onSubmit?: (text: string) => void;
  /** Called after a mention node is inserted. Raw insertText entries do not trigger this. */
  onMentionInsert?: (item: MentionItem) => void;
  /**
   * Controlled mention metadata used to restore serialized @labels as rich inline nodes.
   * Entries absent from the serialized value are ignored.
   */
  mentions?: readonly MentionItem[];
  /**
   * Preferred: typed provider for @ mention suggestions.
   * When both `mentionProvider` and `queryMentions` are provided,
   * `mentionProvider` takes precedence.
   */
  mentionProvider?: ContextMentionProvider;
  /**
   * Optional host renderer for mention pill icons. Used when the host owns
   * provider-specific assets that this package cannot import directly.
   */
  renderMentionIcon?: RenderMentionIcon;
  /**
   * Legacy: async callback that returns @ mention suggestions.
   * Kept for back-compat; prefer `mentionProvider` for new integrations.
   */
  queryMentions?: (query: string) => Promise<MentionItem[]>;
  /**
   * Async callback that returns / command suggestions for the given query.
   * Return an empty array if no commands are available.
   */
  queryCommands?: (query: string) => Promise<CommandItem[]>;
  /** Controlled visibility gate for the command popup. Omit for editor-owned visibility. */
  commandPopupOpen?: boolean;
  /** Called when the command suggestion lifecycle opens or closes. */
  onCommandPopupOpenChange?: (open: boolean) => void;
  /**
   * Called when a / command with behavior='execute' is selected.
   * The trigger range is deleted; text is NOT inserted.
   */
  onCommand?: (item: CommandItem) => void;
  className?: string;
  /**
   * Extra class for the portaled mention/command suggestion popups. They mount
   * under <body>, so hosts that scope theming to a subtree (e.g. the
   * ChatComposer contract bridge) must carry the scope class onto them.
   */
  popupClassName?: string;
}

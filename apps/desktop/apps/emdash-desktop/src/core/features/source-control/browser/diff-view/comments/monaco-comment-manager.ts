import type * as monaco from 'monaco-editor';
import React from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { DraftComment } from '@core/features/source-control/api/browser/diff-view/stores/draft-comments-store';
import { AddCommentButton } from './add-comment-button';
import { CommentInput } from './comment-input';
import { CommentWidget } from './comment-widget';

const COMMENT_ZONE_HEIGHT_PX = 140 + 24;

interface MonacoCommentManagerOptions {
  onAddComment: (lineNumber: number, content: string, lineContent?: string) => void | Promise<void>;
  onEditComment: (id: string, content: string) => void | Promise<void>;
  onDeleteComment: (id: string) => void | Promise<void>;
}

interface GlyphWidgetHandle {
  widget: monaco.editor.IGlyphMarginWidget;
  root: Root;
}

export class MonacoCommentManager {
  private readonly editor: monaco.editor.IStandaloneDiffEditor;
  private readonly options: MonacoCommentManagerOptions;

  private viewZoneRoots: Map<
    string,
    { zoneId: string; root: Root; domNode: HTMLElement; lineNumber: number }
  > = new Map();

  private decorationIds: string[] = [];
  private hoveredLine: number | null = null;

  private hoverWidgetHandle: GlyphWidgetHandle | null = null;
  private pinnedWidgetHandle: GlyphWidgetHandle | null = null;

  private inputZoneId: string | null = null;
  private inputRoot: Root | null = null;
  private inputDomNode: HTMLElement | null = null;
  private activeInputLine: number | null = null;

  private disposed = false;
  private hoverMoveDisposable: monaco.IDisposable | null = null;
  private hoverLeaveDisposable: monaco.IDisposable | null = null;

  constructor(editor: monaco.editor.IStandaloneDiffEditor, options: MonacoCommentManagerOptions) {
    this.editor = editor;
    this.options = options;
    this.setupHoverHandler();
  }

  private createGlyphWidget(
    id: string,
    lineNumber: number,
    pinned: boolean,
    onClick: () => void
  ): GlyphWidgetHandle {
    // oxlint-disable-next-line typescript/no-explicit-any
    const m = (globalThis as any).__monaco as typeof monaco;
    const domNode = document.createElement('div');
    const root = createRoot(domNode);
    root.render(React.createElement(AddCommentButton, { pinned, onClick }));

    const widget: monaco.editor.IGlyphMarginWidget = {
      getId: () => id,
      getDomNode: () => domNode,
      getPosition: () => ({
        lane: m.editor.GlyphMarginLane.Right,
        zIndex: 10,
        range: {
          startLineNumber: lineNumber,
          startColumn: 1,
          endLineNumber: lineNumber,
          endColumn: 1,
        },
      }),
    };

    return { widget, root };
  }

  private removeGlyphWidgetHandle(handle: GlyphWidgetHandle): void {
    const modifiedEditor = this.editor.getModifiedEditor();
    modifiedEditor.removeGlyphMarginWidget(handle.widget);
    handle.root.unmount();
  }

  private setupHoverHandler() {
    const modifiedEditor = this.editor.getModifiedEditor();

    this.hoverMoveDisposable = modifiedEditor.onMouseMove((e) => {
      if (this.disposed) return;
      const targetElement = e.target.element as HTMLElement | null;
      if (targetElement?.closest?.('.comment-view-zone')) {
        this.clearHoverWidget();
        this.hoveredLine = null;
        return;
      }

      const lineNumber = e.target.position?.lineNumber;

      if (lineNumber && lineNumber !== this.hoveredLine) {
        if (lineNumber === this.activeInputLine) {
          this.clearHoverWidget();
          this.hoveredLine = lineNumber;
          return;
        }
        this.setHoverWidget(lineNumber);
        this.hoveredLine = lineNumber;
      } else if (!lineNumber && this.hoveredLine !== null) {
        this.clearHoverWidget();
        this.hoveredLine = null;
      }
    });

    this.hoverLeaveDisposable = modifiedEditor.onMouseLeave(() => {
      if (this.disposed) return;
      this.clearHoverWidget();
      this.hoveredLine = null;
    });
  }

  private setHoverWidget(lineNumber: number): void {
    const modifiedEditor = this.editor.getModifiedEditor();
    if (this.hoverWidgetHandle) {
      this.removeGlyphWidgetHandle(this.hoverWidgetHandle);
      this.hoverWidgetHandle = null;
    }
    const handle = this.createGlyphWidget('comment-add-hover', lineNumber, false, () => {
      const model = modifiedEditor.getModel();
      const lineContent = model?.getLineContent(lineNumber) ?? '';
      this.showInputAt(lineNumber, lineContent);
    });
    modifiedEditor.addGlyphMarginWidget(handle.widget);
    this.hoverWidgetHandle = handle;
  }

  private clearHoverWidget(): void {
    if (!this.hoverWidgetHandle) return;
    this.removeGlyphWidgetHandle(this.hoverWidgetHandle);
    this.hoverWidgetHandle = null;
  }

  setComments(comments: DraftComment[]) {
    if (this.disposed) return;

    const modifiedEditor = this.editor.getModifiedEditor();
    const nextById = new Map<string, DraftComment>(
      comments.map((comment) => [comment.id, comment])
    );

    this.decorationIds = modifiedEditor.deltaDecorations(this.decorationIds, []);

    modifiedEditor.changeViewZones((accessor) => {
      for (const [commentId, zoneInfo] of Array.from(this.viewZoneRoots.entries())) {
        if (!nextById.has(commentId)) {
          accessor.removeZone(zoneInfo.zoneId);
          zoneInfo.root.unmount();
          this.viewZoneRoots.delete(commentId);
        }
      }

      for (const comment of comments) {
        const existing = this.viewZoneRoots.get(comment.id);
        if (existing) {
          existing.domNode.dataset.lineNumber = String(comment.lineNumber);
          existing.domNode.style.padding = '12px';
          existing.domNode.style.boxSizing = 'border-box';
          existing.domNode.className = 'comment-view-zone bg-background-2/40 border border-border';

          existing.root.render(
            React.createElement(CommentWidget, {
              comment,
              onEdit: (content) => this.options.onEditComment(comment.id, content),
              onDelete: () => this.options.onDeleteComment(comment.id),
            })
          );

          if (existing.lineNumber !== comment.lineNumber) {
            accessor.removeZone(existing.zoneId);
            const zoneId = accessor.addZone({
              afterLineNumber: comment.lineNumber,
              heightInPx: COMMENT_ZONE_HEIGHT_PX,
              domNode: existing.domNode,
              suppressMouseDown: false,
              showInHiddenAreas: true,
            });
            this.viewZoneRoots.set(comment.id, {
              ...existing,
              zoneId,
              lineNumber: comment.lineNumber,
            });
          }
          continue;
        }

        const domNode = document.createElement('div');
        domNode.style.padding = '12px';
        domNode.style.boxSizing = 'border-box';
        domNode.className = 'comment-view-zone bg-background-2/40 border border-border';
        domNode.style.pointerEvents = 'auto';
        domNode.style.position = 'relative';
        domNode.style.zIndex = '10';
        domNode.style.width = '100%';
        domNode.dataset.lineNumber = String(comment.lineNumber);

        const root = createRoot(domNode);
        root.render(
          React.createElement(CommentWidget, {
            comment,
            onEdit: (content) => this.options.onEditComment(comment.id, content),
            onDelete: () => this.options.onDeleteComment(comment.id),
          })
        );

        const zoneId = accessor.addZone({
          afterLineNumber: comment.lineNumber,
          heightInPx: COMMENT_ZONE_HEIGHT_PX,
          domNode,
          suppressMouseDown: false,
          showInHiddenAreas: true,
        });

        this.viewZoneRoots.set(comment.id, {
          zoneId,
          root,
          domNode,
          lineNumber: comment.lineNumber,
        });
      }
    });
  }

  showInputAt(lineNumber: number, lineContent: string) {
    if (this.activeInputLine === lineNumber && this.inputDomNode) {
      const textarea = this.inputDomNode.querySelector('textarea');
      if (textarea instanceof HTMLTextAreaElement) textarea.focus();
      return;
    }

    this.hideInput();

    const modifiedEditor = this.editor.getModifiedEditor();
    this.activeInputLine = lineNumber;

    // Show pinned widget at the active input line
    const pinnedHandle = this.createGlyphWidget('comment-add-pinned', lineNumber, true, () =>
      this.showInputAt(lineNumber, lineContent)
    );
    modifiedEditor.addGlyphMarginWidget(pinnedHandle.widget);
    this.pinnedWidgetHandle = pinnedHandle;

    this.inputDomNode = document.createElement('div');
    this.inputRoot = createRoot(this.inputDomNode);

    this.inputRoot.render(
      React.createElement(CommentInput, {
        lineNumber,
        onSubmit: async (content) => {
          await this.options.onAddComment(lineNumber, content, lineContent);
          this.hideInput();
        },
        onCancel: () => this.hideInput(),
      })
    );

    this.inputDomNode.style.padding = '12px';
    this.inputDomNode.style.boxSizing = 'border-box';
    this.inputDomNode.className = 'comment-view-zone bg-background-2/40 border border-border';
    this.inputDomNode.style.pointerEvents = 'auto';
    this.inputDomNode.style.position = 'relative';
    this.inputDomNode.style.zIndex = '10';
    this.inputDomNode.style.width = '100%';
    this.inputDomNode.dataset.lineNumber = String(lineNumber);

    modifiedEditor.changeViewZones((accessor) => {
      this.inputZoneId = accessor.addZone({
        afterLineNumber: lineNumber,
        heightInPx: COMMENT_ZONE_HEIGHT_PX,
        domNode: this.inputDomNode!,
        suppressMouseDown: false,
        showInHiddenAreas: true,
      });
    });

    const focusTextarea = () => {
      const textarea = this.inputDomNode?.querySelector('textarea');
      if (textarea instanceof HTMLTextAreaElement) {
        textarea.focus();
        textarea.select();
      }
    };

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        focusTextarea();
      });
    });
    setTimeout(() => {
      focusTextarea();
    }, 80);
  }

  hideInput() {
    const modifiedEditor = this.editor.getModifiedEditor();
    if (this.inputZoneId) {
      modifiedEditor.changeViewZones((accessor) => {
        accessor.removeZone(this.inputZoneId!);
      });
      this.inputZoneId = null;
    }

    this.inputRoot?.unmount();
    this.inputRoot = null;
    this.inputDomNode = null;
    this.activeInputLine = null;

    if (this.pinnedWidgetHandle) {
      this.removeGlyphWidgetHandle(this.pinnedWidgetHandle);
      this.pinnedWidgetHandle = null;
    }
  }

  dispose() {
    this.disposed = true;

    this.hoverMoveDisposable?.dispose();
    this.hoverLeaveDisposable?.dispose();

    if (this.hoverWidgetHandle) {
      this.removeGlyphWidgetHandle(this.hoverWidgetHandle);
      this.hoverWidgetHandle = null;
    }

    this.hideInput();

    const modifiedEditor = this.editor.getModifiedEditor();
    this.decorationIds = modifiedEditor.deltaDecorations(this.decorationIds, []);

    modifiedEditor.changeViewZones((accessor) => {
      for (const zone of this.viewZoneRoots.values()) {
        accessor.removeZone(zone.zoneId);
        zone.root.unmount();
      }
    });
    this.viewZoneRoots.clear();
  }
}

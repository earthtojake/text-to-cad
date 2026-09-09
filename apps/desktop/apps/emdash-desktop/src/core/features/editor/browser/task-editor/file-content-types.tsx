/**
 * FILE_CONTENT_TYPES — single source of truth for file rendering capabilities.
 *
 * Each entry declares:
 *   editable  — true when the file has a Monaco source view (text/csv/markdown/html/svg)
 *   Preview   — present when the file has a rendered preview component
 *
 * The FileContent container derives showSource / showPreview / canToggle from these
 * two flags plus FileTabResource.viewMode. Load-time states (loading, errors,
 * orphaned) are not kinds: they come from the tab's OpenFileStore entry and render
 * as FileStatusPlaceholder above this map.
 */

import { Spinner } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useEffect, useState, type ComponentType } from 'react';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { HtmlRenderer } from '@core/features/editor/contributions/browser/renderers/html-renderer';
import { readImageFile } from '@core/features/files/api/browser/file-content';
import { BinaryRenderer } from '../renderers/binary-renderer';
import { CsvRenderer } from '../renderers/csv-renderer';
import { ImageRenderer } from '../renderers/image-renderer';
import { MarkdownEditorRenderer } from '../renderers/markdown-renderer';
import { SvgRenderer } from '../renderers/svg-renderer';
import type { ManagedFileKind } from '../renderers/types';

export interface FileContentTypeDef {
  /** True when the file type supports Monaco source editing. */
  editable: boolean;
  /** Present when the file type has a rendered preview component. */
  Preview?: ComponentType<{ tab: FileTabResource }>;
}

// Stable wrapper components so React never sees a new reference on re-render.

function CsvPreview({ tab }: { tab: FileTabResource }) {
  return <CsvRenderer tab={tab} />;
}

function MarkdownPreview({ tab }: { tab: FileTabResource }) {
  return <MarkdownEditorRenderer tab={tab} />;
}

function HtmlPreview({ tab }: { tab: FileTabResource }) {
  return <HtmlRenderer tab={tab} />;
}

function SvgPreview({ tab }: { tab: FileTabResource }) {
  return <SvgRenderer tab={tab} />;
}

/**
 * Raster images bypass the text-content stack: the preview reads the bytes
 * itself as a data URL (the store classifies binary content as an error).
 */
const ImagePreview = observer(function ImagePreview({ tab }: { tab: FileTabResource }) {
  const [state, setState] = useState<
    { kind: 'loading' } | { kind: 'ready'; dataUrl: string } | { kind: 'error' }
  >({ kind: 'loading' });
  const ref = tab.ref;

  useEffect(() => {
    if (!ref) {
      setState({ kind: 'error' });
      return;
    }
    let cancelled = false;
    setState({ kind: 'loading' });
    void readImageFile(ref)
      .then((result) => {
        if (cancelled) return;
        if (result.success && !result.data.truncated) {
          setState({ kind: 'ready', dataUrl: result.data.dataUrl });
        } else {
          setState({ kind: 'error' });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, [ref]);

  if (state.kind === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size="sm" />
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <div className="flex h-full items-center justify-center text-xs text-foreground-passive">
        Could not load image
      </div>
    );
  }
  return <ImageRenderer file={{ path: tab.path, content: state.dataUrl }} />;
});

const PdfPreview = observer(function PdfPreview({ tab }: { tab: FileTabResource }) {
  const [state, setState] = useState<
    { kind: 'loading' } | { kind: 'ready'; dataUrl: string } | { kind: 'error' }
  >({ kind: 'loading' });
  const ref = tab.ref;

  useEffect(() => {
    if (!ref) {
      setState({ kind: 'error' });
      return;
    }
    let cancelled = false;
    setState({ kind: 'loading' });
    void readImageFile(ref)
      .then((result) => {
        if (cancelled) return;
        if (result.success && !result.data.truncated) {
          setState({ kind: 'ready', dataUrl: result.data.dataUrl });
        } else {
          setState({ kind: 'error' });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, [ref]);

  if (state.kind === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size="sm" />
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <div className="flex h-full items-center justify-center text-xs text-foreground-passive">
        Could not load PDF
      </div>
    );
  }
  return <iframe title={tab.displayPath} src={state.dataUrl} className="h-full w-full bg-white" />;
});

function BinaryPreview({ tab }: { tab: FileTabResource }) {
  return <BinaryRenderer file={tab} />;
}

export const FILE_CONTENT_TYPES: Record<
  Exclude<ManagedFileKind, 'too-large'>,
  FileContentTypeDef
> = {
  text: { editable: true },
  csv: { editable: true, Preview: CsvPreview },
  markdown: { editable: true, Preview: MarkdownPreview },
  html: { editable: true, Preview: HtmlPreview },
  svg: { editable: true, Preview: SvgPreview },
  image: { editable: false, Preview: ImagePreview },
  pdf: { editable: false, Preview: PdfPreview },
  binary: { editable: false, Preview: BinaryPreview },
};

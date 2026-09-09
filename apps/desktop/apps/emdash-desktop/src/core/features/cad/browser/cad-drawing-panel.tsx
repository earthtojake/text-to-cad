import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import { Button, DropdownMenu } from '@emdash/ui/react/primitives';
import {
  ArrowUpRight,
  Download,
  FileOutput,
  Loader2,
  MoreHorizontal,
  RefreshCw,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { getFilesClient } from '@core/features/files/api/browser/client';
import { PREVIEW_MAX_BYTES } from '@core/features/files/api/browser/file-content';
import { openWithOS } from '@core/features/workbench/api/browser/open-with-os';
import { useWorkspace } from '@core/features/workbench/api/browser/task-composition-context';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import type { CadModelFile } from './cad-model-files-model';

type DrawingPreview =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'unsupported' }
  | { status: 'ready'; url: string; mimeType: string };

type DrawingManifest = { revisionId: string | null };

export function CadDrawingPanel({
  drawings,
  regenerating,
  onRegenerate,
}: {
  drawings: readonly CadModelFile[];
  regenerating: boolean;
  onRegenerate: () => void;
}) {
  const workspace = useWorkspace();
  const selected = preferredDrawing(drawings);
  const previewPath = selected?.path;
  const [preview, setPreview] = useState<DrawingPreview>({ status: 'loading' });
  const [manifest, setManifest] = useState<DrawingManifest>({ revisionId: null });
  const pdf = drawings.find((drawing) => drawing.path.toLowerCase().endsWith('.pdf'));
  const dxf = drawings.find((drawing) => drawing.path.toLowerCase().endsWith('.dxf'));

  useEffect(() => {
    if (!previewPath) {
      setPreview({ status: 'unsupported' });
      return;
    }
    if (!isPreviewableDrawing(previewPath)) {
      setPreview({ status: 'unsupported' });
      return;
    }

    let disposed = false;
    let objectUrl: string | null = null;
    setPreview({ status: 'loading' });
    void (async () => {
      const result = await (
        await getFilesClient()
      ).fs.readBytes({
        uri: encodeResourceUri(hostFileRefFromNativePath(previewPath, workspace.sshConnectionId)),
        options: { maxBytes: PREVIEW_MAX_BYTES },
      });
      if (disposed) return;
      if (!result.success) {
        setPreview({ status: 'error', message: 'The drawing could not be loaded.' });
        return;
      }
      if (result.data.meta.truncated) {
        setPreview({ status: 'error', message: 'The drawing is too large to preview.' });
        return;
      }
      const bytes = await result.data.bytes();
      if (disposed) return;
      const buffer = new ArrayBuffer(bytes.byteLength);
      new Uint8Array(buffer).set(bytes);
      const mimeType = drawingMimeType(previewPath);
      objectUrl = URL.createObjectURL(new Blob([buffer], { type: mimeType }));
      setPreview({ status: 'ready', url: objectUrl, mimeType });
    })().catch((error) => {
      if (!disposed) {
        setPreview({
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        });
      }
    });

    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewPath, workspace.sshConnectionId]);

  useEffect(() => {
    if (!previewPath) return;
    let disposed = false;
    setManifest({ revisionId: null });
    void (async () => {
      const result = await (
        await getFilesClient()
      ).fs.readText({
        uri: encodeResourceUri(
          hostFileRefFromNativePath(drawingManifestPath(previewPath), workspace.sshConnectionId)
        ),
        options: { maxBytes: 64 * 1024 },
      });
      if (disposed || !result.success || result.data.truncated) return;
      const value = JSON.parse(result.data.content) as {
        model?: { revisionId?: unknown };
      };
      setManifest({
        revisionId: typeof value.model?.revisionId === 'string' ? value.model.revisionId : null,
      });
    })().catch(() => {});
    return () => {
      disposed = true;
    };
  }, [previewPath, workspace.sshConnectionId]);

  if (!selected) return null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-background-secondary">
      <div className="@container flex h-10 shrink-0 items-center gap-2 border-b bg-background px-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <FileOutput className="size-3.5 shrink-0" />
          <span className="truncate text-sm font-medium" title="Engineering drawing">
            Engineering drawing
          </span>
          {manifest.revisionId ? (
            <span
              className="shrink-0 text-micro text-foreground-muted @max-[520px]:hidden"
              title={`Revision ${manifest.revisionId.replace('sha256:', '')}`}
            >
              Revision {manifest.revisionId.replace('sha256:', '').slice(0, 12)}
            </span>
          ) : null}
        </div>
        <div className="hidden shrink-0 items-center gap-1 @min-[601px]:flex">
          {pdf ? <DrawingFileButton drawing={pdf} label="PDF" /> : null}
          {dxf ? <DrawingFileButton drawing={dxf} label="DXF" /> : null}
        </div>
        <Button
          type="button"
          size="xs"
          variant="ghost"
          className="shrink-0"
          disabled={regenerating}
          onClick={onRegenerate}
        >
          {regenerating ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          {regenerating ? 'Updating…' : 'Update'}
        </Button>
        <div className="hidden shrink-0 @min-[601px]:block">
          <Button
            type="button"
            size="xs"
            variant="ghost"
            onClick={() => void openWithOS(selected.path)}
          >
            <ArrowUpRight className="size-3.5" />
            Open {drawingFormatLabel(selected.path)}
          </Button>
        </div>
        <div className="hidden shrink-0 @max-[600px]:block">
          <DropdownMenu.Root>
            <DropdownMenu.Trigger
              render={
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  icon
                  aria-label="More drawing actions"
                >
                  <MoreHorizontal className="size-3.5" />
                </Button>
              }
            />
            <DropdownMenu.Content align="end">
              {pdf ? <DrawingFileMenuItem drawing={pdf} label="PDF" /> : null}
              {dxf ? <DrawingFileMenuItem drawing={dxf} label="DXF" /> : null}
              {pdf || dxf ? <DropdownMenu.Separator /> : null}
              <DropdownMenu.Item onClick={() => void openWithOS(selected.path)}>
                <ArrowUpRight className="size-4" />
                Open {drawingFormatLabel(selected.path)}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      </div>

      <div className="min-h-0 flex-1 p-3">
        {preview.status === 'loading' ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-foreground-muted">
            <Loader2 className="size-4 animate-spin" /> Loading drawing…
          </div>
        ) : preview.status === 'error' ? (
          <div className="flex h-full items-center justify-center text-sm text-foreground-destructive">
            {preview.message}
          </div>
        ) : preview.status === 'ready' && preview.mimeType === 'application/pdf' ? (
          <iframe
            title={selected.name}
            src={preview.url}
            className="h-full w-full rounded-lg border bg-white"
          />
        ) : preview.status === 'ready' ? (
          <div className="flex h-full items-center justify-center overflow-auto rounded-lg border bg-background p-4">
            <img
              src={preview.url}
              alt={selected.name}
              className="max-h-full max-w-full object-contain"
            />
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center rounded-lg border bg-background text-center">
            <FileOutput className="size-7 text-foreground-muted" />
            <div className="mt-3 text-sm font-medium text-foreground">Drawing ready</div>
            <p className="mt-1 max-w-sm text-xs leading-5 text-foreground-muted">
              {selected.name} is linked to this model. Open it in its drawing application for full
              editing.
            </p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="mt-4"
              onClick={() => void openWithOS(selected.path)}
            >
              <ArrowUpRight className="size-3.5" />
              Open drawing
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function isPreviewableDrawing(path: string): boolean {
  return /\.(?:pdf|svg|png|jpe?g|webp)$/i.test(path);
}

function drawingMimeType(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith('.pdf')) return 'application/pdf';
  if (lower.endsWith('.svg')) return 'image/svg+xml';
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  return 'image/jpeg';
}

function preferredDrawing(drawings: readonly CadModelFile[]): CadModelFile | undefined {
  return (
    drawings.find((drawing) => drawing.path.toLowerCase().endsWith('.svg')) ??
    drawings.find((drawing) => drawing.path.toLowerCase().endsWith('.pdf')) ??
    drawings.find((drawing) => isPreviewableDrawing(drawing.path)) ??
    drawings[0]
  );
}

function drawingManifestPath(path: string): string {
  return path.replace(/\.(?:svg|pdf|dxf)$/i, '.json');
}

function drawingFormatLabel(path: string): string {
  return path.split('.').at(-1)?.toUpperCase() || 'drawing';
}

function DrawingFileButton({ drawing, label }: { drawing: CadModelFile; label: string }) {
  return (
    <Button
      type="button"
      size="xs"
      variant="ghost"
      className="shrink-0"
      onClick={() => void openWithOS(drawing.path)}
    >
      <Download className="size-3.5" />
      {label}
    </Button>
  );
}

function DrawingFileMenuItem({ drawing, label }: { drawing: CadModelFile; label: string }) {
  return (
    <DropdownMenu.Item onClick={() => void openWithOS(drawing.path)}>
      <Download className="size-4" />
      Open {label}
    </DropdownMenu.Item>
  );
}

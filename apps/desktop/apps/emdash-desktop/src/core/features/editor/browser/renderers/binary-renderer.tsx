import { FileQuestion } from 'lucide-react';

interface BinaryRendererProps {
  file: { path: string };
}

/** Shown for binary or otherwise unsupported files. */
export function BinaryRenderer({ file }: BinaryRendererProps) {
  const fileName = file.path.split('/').pop() ?? file.path;
  const ext = file.path.split('.').pop()?.toUpperCase();

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-foreground-muted">
      <FileQuestion className="h-10 w-10 opacity-30" />
      <div className="text-center">
        <p className="text-sm font-medium">{fileName}</p>
        {ext && <p className="mt-0.5 text-xs opacity-50">{ext} file</p>}
        <p className="mt-1 text-xs opacity-70">Binary file — no preview available</p>
      </div>
    </div>
  );
}

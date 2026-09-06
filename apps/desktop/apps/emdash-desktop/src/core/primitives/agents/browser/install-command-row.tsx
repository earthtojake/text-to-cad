import { Check, Copy } from 'lucide-react';
import React, { useCallback, useState } from 'react';
import type { InstallMethod } from '@core/primitives/agents/api';
import { cn } from '@core/primitives/styling/browser/cn';

export function humanizeMethod(method: InstallMethod): string {
  const labels: Record<InstallMethod, string> = {
    'installer-macos': 'macOS Installer',
    'installer-windows': 'Windows Installer',
    'installer-linux': 'Linux Installer',
    homebrew: 'Homebrew',
    winget: 'winget',
    powershell: 'PowerShell',
    npm: 'npm',
    apt: 'apt',
    curl: 'curl',
    pip: 'pip',
    cargo: 'cargo',
    other: 'Other',
  };
  return labels[method] ?? method;
}

export function CopyButton({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [command]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="shrink-0 rounded p-1 text-foreground-passive opacity-0 transition-opacity group-hover:opacity-100 hover:bg-background-2 hover:text-foreground"
      aria-label="Copy command"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-foreground-success" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

export function CommandRow({ command, action }: { command: string; action: React.ReactNode }) {
  return (
    <div className="flex w-full items-stretch gap-[2px]">
      <div
        className={cn(
          'group flex min-w-0 flex-1 items-center gap-2 bg-background-quaternary-1 px-2 py-1.5',
          action ? 'rounded-l-lg' : 'rounded-lg'
        )}
      >
        <code className="min-w-0 flex-1 truncate font-mono text-xs text-foreground-muted">
          {command}
        </code>
        <CopyButton command={command} />
      </div>
      {action}
    </div>
  );
}

export function CommandActionButton({ ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className="group flex items-center gap-2 rounded-r-lg bg-background-quaternary-1 px-4 text-sm hover:bg-background-quaternary-2 disabled:cursor-not-allowed disabled:text-foreground-passive disabled:hover:bg-background-quaternary-1"
      {...props}
    />
  );
}

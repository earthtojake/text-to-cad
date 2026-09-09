import { Button } from '@emdash/ui/react/primitives';
import React from 'react';
import { getMementoClient } from '@core/primitives/mementos/browser';

type ErrorBoundaryState = {
  hasError: boolean;
  error: Error | null;
};

type ErrorBoundaryProps = {
  children?: React.ReactNode;
};

function ErrorFallback({ message, onReload }: { message: string; onReload: () => void }) {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background p-6">
      <div className="max-w-xl rounded-md border border-border bg-background p-6 text-foreground shadow-sm">
        <h1 className="mb-2 text-lg font-semibold">Something went wrong</h1>
        <p className="mb-4 text-sm break-all text-foreground-muted">{message}</p>
        <Button variant="primary" onClick={onReload}>
          Reload
        </Button>
      </div>
    </div>
  );
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  handleReload = () => {
    void Promise.resolve()
      .then(async () => await getMementoClient().deleteAll())
      .catch(() => {})
      .finally(() => {
        try {
          window.location.reload();
        } catch {}
      });
  };

  render() {
    if (!this.state.hasError) return this.props.children as React.ReactElement;
    const message = this.state.error?.message || 'An unexpected error occurred.';
    return <ErrorFallback message={message} onReload={this.handleReload} />;
  }
}

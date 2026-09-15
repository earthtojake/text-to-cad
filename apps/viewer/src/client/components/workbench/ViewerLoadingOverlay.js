import LoadingIndicator from "./LoadingIndicator";

export default function ViewerLoadingOverlay({ loading, previewMode, operationKey }) {
  if (!loading?.opening || previewMode) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
      <div className="cad-loading-overlay absolute inset-0" />
      <div className="absolute inset-0 flex items-center justify-center px-4 text-popover-foreground">
        <LoadingIndicator headline={loading.headline} progress={loading.progress} operationKey={operationKey} />
      </div>
    </div>
  );
}

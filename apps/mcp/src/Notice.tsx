/** A line over the view, the model still under it: what stopped working, and what to do about it. */
export function Banner({ message }: { message: string }) {
  // Below the navbar row, so it never sits over its controls.
  return <div className="pointer-events-none absolute inset-x-0 top-12 z-50 flex justify-center px-3">
    <div className="pointer-events-auto max-w-md rounded-md border bg-background/95 px-3 py-2 text-ui text-xs text-foreground shadow-sm" role="alert">{message}</div>
  </div>;
}

/** A whole-page message: why CAD cannot show anything, and what to do about it. */
export default function Notice({ title, message, details }: { title: string; message: string; details?: string }) {
  return <div className="cad-notice text-ui" role="alert">
    <div className="flex max-w-md flex-col items-start gap-3">
      <h1 className="text-base font-medium">{title}</h1>
      <p className="text-muted-foreground">{message}</p>
      {details && <details className="w-full text-tiny text-muted-foreground"><summary className="cursor-pointer">Details</summary><pre className="mt-2 whitespace-pre-wrap break-all select-text">{details}</pre></details>}
    </div>
  </div>;
}

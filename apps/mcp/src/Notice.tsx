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

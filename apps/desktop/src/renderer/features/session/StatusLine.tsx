import { Shimmer } from "@renderer/components/ai-elements/shimmer";

/**
 * The live italic line at the bottom of a running turn (plan §2):
 * "Running ls -la", "Thinking", "Waiting for your approval". The text is
 * `statusLine()` in view.ts; this only draws it.
 */
export function StatusLine({ text }: { text: string }) {
  return (
    <p className="not-prose mt-1 px-1.5 text-[13px] leading-5 italic" data-status-line>
      <Shimmer as="span">{text}</Shimmer>
    </p>
  );
}

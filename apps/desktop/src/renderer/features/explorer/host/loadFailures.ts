import { createPromptContext, textPart } from "@text-to-cad/core/prompt";
import type { PromptContextPort } from "@text-to-cad/core/prompt";
import type { ClipboardPort, ViewerHost, ViewerLoadFailure } from "@text-to-cad/ui/host";
import { runtimeKernelNote } from "../adapters/cadRuntime";

type Class = "build" | "network" | "load" | "empty" | "edit" | "other";

/** What went wrong, by the alert's kind: each is described and handed to the agent differently. */
function classOf(kind: string | undefined): Class {
  switch (kind) {
    case "compile": case "artifact": case "service": case "http": case "response": return "build";
    case "network": return "network";
    case "mesh": return "load";
    case "empty": return "empty";
    case "edit": return "edit";
    default: return "other";
  }
}

const named = (failure: ViewerLoadFailure) => failure.file ? `“${failure.file}”` : "this file";

/** The diagnostic as the agent receives it: what failed, what to do about it, and the complete output. */
export function loadFailurePrompt(failure: ViewerLoadFailure): string {
  const file = named(failure);
  const ask = {
    build: `The CAD runtime could not build ${file}: ${failure.title}. Fix the source so it builds, then rebuild it.`,
    network: `The CAD viewer lost contact with the CAD runtime while loading ${file}. Find out why.`,
    load: `The CAD viewer could not read ${file}: ${failure.title}. Check that the file is complete and valid, and regenerate it if it is not.`,
    empty: `${file} loaded but contains no geometry to display. Check that the model is written out completely, and regenerate it if it is not.`,
    edit: `A live edit of ${file} failed: ${failure.title}. Fix the model so the update applies, then run it again.`,
    other: `The CAD viewer could not display ${file}: ${failure.title}. Find out why and fix it.`,
  }[classOf(failure.kind)];
  const diagnostic = failure.details || failure.reason || failure.message || failure.title;
  return `${ask}\n\n\`\`\`\n${diagnostic}\n\`\`\``;
}

/** A build failure's next step; first, when the runtime has one, its CAD kernel warning. */
function buildRecovery(): string {
  const kernel = runtimeKernelNote();
  if (!kernel) return "Ask the agent to fix the source, or copy the details.";
  // A check that timed out is no reason to change the source.
  return kernel.timedOut
    ? `${kernel.note}. Run Repair in Settings › About, then Try again; or copy the details.`
    : `${kernel.note}. Ask the agent to fix the source, or copy the details.`;
}

/**
 * The desktop has no viewer terminal or address to check: the runtime is in the app, and
 * the next step is the session's agent. A build failure says the runtime reported it, with
 * the interpreter's words beneath; a lost connection names the runtime; any other failure
 * keeps the card's own words. Every failure offers the diagnostic to the session's prompt
 * (the same delivery "Add to prompt" uses, unavailable while that session is) and to the
 * clipboard, beside Try again.
 */
export function createDesktopLoadFailures(promptContext: PromptContextPort, clipboard: ClipboardPort): NonNullable<ViewerHost["loadFailures"]> {
  return {
    recover(failure) {
      const kept = failure.blocking ? "" : " The previous version stays on screen.";
      const text = loadFailurePrompt(failure);
      const kind = classOf(failure.kind);
      const words = kind === "build"
        ? { message: `The CAD runtime reported an error building ${named(failure)}.${kept}`, recovery: buildRecovery() }
        : kind === "network"
          ? { message: `The app lost contact with the CAD runtime while loading ${named(failure)}.${kept}`, recovery: "Try again. If it keeps happening, copy the details." }
          : {};
      const destination = promptContext.getSnapshot();
      return {
        ...words,
        actions: [
          {
            label: "Ask the agent to fix",
            ...(destination.available ? {} : { disabled: true, reason: destination.reason ?? "This tab's session can't take a prompt." }),
            run: async () => {
              const result = await promptContext.deliver(createPromptContext([textPart(text, "load-failure")]));
              if (result.status === "failed" || result.status === "partial") throw new Error(result.message || "Could not add the error to the prompt.");
              // A destination that went away mid-delivery cancels with its reason.
              return result.status === "added" ? "Added to the prompt." : "message" in result ? result.message ?? "" : "";
            },
          },
          {
            label: "Copy details",
            run: async () => { await clipboard.writeText(failure.details || text); return "Copied."; },
          },
        ],
      };
    },
  };
}

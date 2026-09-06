import { Check, ShieldQuestion, X } from "lucide-react";

import {
  Confirmation,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRequest,
  ConfirmationTitle,
} from "@renderer/components/ai-elements/confirmation";
import { useAcp } from "@renderer/state/acp";
import type { PermissionOption, PermissionRequestPart } from "@shared/acp/types";

/**
 * A `session/request_permission` as AI Elements' Confirmation: the title
 * and description the adapter sent in `_meta`, and one button per option
 * the agent offered — its own ids, its own names — so "Yes, always" means
 * whatever the agent means by it (plan §6).
 *
 * Once answered the card folds to one activity-sized line, so the
 * transcript still says what was decided without taking the room the
 * question did.
 */
export function PermissionCard({ part, sessionId }: { part: PermissionRequestPart; sessionId: string }) {
  const respond = useAcp((state) => state.respondPermission);
  const outcome = part.outcome;

  if (outcome.state !== "pending") {
    const chosen =
      outcome.state === "selected"
        ? (part.options.find((option) => option.optionId === outcome.optionId) ?? null)
        : null;
    const approved = chosen ? chosen.kind === "allow_once" || chosen.kind === "allow_always" : false;
    const verdict =
      outcome.state === "cancelled"
        ? "Cancelled"
        : approved
          ? `Allowed${chosen ? ` — ${chosen.name}` : ""}`
          : `Rejected${chosen ? ` — ${chosen.name}` : ""}`;
    return (
      <div
        className="not-prose flex items-center gap-2 px-1.5 py-1 text-[13px] leading-5 text-muted-foreground"
        data-outcome={outcome.state}
        data-permission={part.requestId}
      >
        <span className="flex size-4 items-center justify-center">
          {approved ? <Check className="size-3.5" /> : <X className="size-3.5" />}
        </span>
        <span className="min-w-0 flex-1 truncate">
          {verdict}
          {part.title ? <span className="text-muted-foreground/70"> · {part.title}</span> : null}
        </span>
      </div>
    );
  }

  return (
    <Confirmation
      approval={{ id: part.requestId }}
      className="not-prose my-2 gap-3 bg-card px-4 py-3 text-[13px] shadow-xs"
      data-outcome="pending"
      data-permission={part.requestId}
      state="approval-requested"
    >
      <ConfirmationTitle className="flex items-start gap-2.5 leading-5">
        <ConfirmationRequest>
          <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center text-muted-foreground">
            <ShieldQuestion className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-medium text-foreground">{part.title ?? "Permission requested"}</span>
            {part.description ? (
              <span className="mt-0.5 block text-muted-foreground">{part.description}</span>
            ) : null}
          </span>
        </ConfirmationRequest>
      </ConfirmationTitle>
      <ConfirmationActions className="flex-wrap justify-end gap-2">
        {orderOptions(part.options).map((option) => (
          <ConfirmationAction
            className="h-7 px-2.5 text-[12px]"
            key={option.optionId}
            onClick={() => void respond(sessionId, part.requestId, option.optionId)}
            title={option.description ?? undefined}
            variant={variantFor(option)}
          >
            {option.name}
          </ConfirmationAction>
        ))}
      </ConfirmationActions>
    </Confirmation>
  );
}

/** Allow first, reject last — the order Codex lays its buttons out in. */
function orderOptions(options: PermissionOption[]): PermissionOption[] {
  const rank: Record<PermissionOption["kind"], number> = {
    allow_once: 0,
    allow_always: 1,
    reject_once: 2,
    reject_always: 3,
  };
  return [...options].sort((a, b) => rank[a.kind] - rank[b.kind]);
}

function variantFor(option: PermissionOption): "default" | "outline" | "ghost" {
  switch (option.kind) {
    case "allow_once":
      return "default";
    case "allow_always":
      return "outline";
    default:
      return "ghost";
  }
}

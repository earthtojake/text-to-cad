import { Bot, GitBranch, Paperclip, ShieldCheck } from "lucide-react";

import {
  PromptInput,
  PromptInputButton,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@renderer/components/ai-elements/prompt-input";

/**
 * The composer, built from AI Elements' Prompt Input so P2 inherits its
 * attachment handling, drag-and-drop and submit semantics rather than
 * re-implementing them.
 *
 * P0 wires nothing: submitting does nothing because there is no session to
 * submit to yet. The chips are the ones plan §6 calls for — agent, project and
 * git mode, approval mode — shown disabled so the shape of the row is settled
 * before P1 fills them in.
 */
export function Composer({ projectName }: { projectName: string | null }) {
  return (
    <PromptInput
      className="rounded-2xl shadow-sm"
      onSubmit={() => {
        // P1 owns `session/prompt`.
      }}
    >
      {/*
       * Deliberately no <PromptInputBody>: it renders `display: contents`, and
       * the InputGroup underneath stacks itself with
       * `has-[>[data-align=block-end]]:flex-col` — a direct-child selector that
       * `display: contents` does not satisfy. Wrapped, the composer collapses
       * into one 36px row with the textarea crushed against the tools.
       */}
      <PromptInputTextarea
        disabled
        placeholder={projectName ? "Do anything" : "Add a project to start a session"}
      />
      <PromptInputFooter>
        <PromptInputTools>
          <PromptInputButton disabled tooltip="Attach files">
            <Paperclip className="size-4" />
          </PromptInputButton>
          <PromptInputButton disabled size="sm">
            <Bot className="size-4" />
            Agent
          </PromptInputButton>
          <PromptInputButton disabled size="sm">
            <GitBranch className="size-4" />
            {projectName ?? "No project"}
          </PromptInputButton>
          <PromptInputButton disabled size="sm">
            <ShieldCheck className="size-4" />
            Approve for me
          </PromptInputButton>
        </PromptInputTools>
        <PromptInputSubmit disabled />
      </PromptInputFooter>
    </PromptInput>
  );
}

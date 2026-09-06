import { buildPromptInjectionPayload } from '@core/primitives/prompt-injection/api/prompt-injection';

export { buildPromptInjectionPayload } from '@core/primitives/prompt-injection/api/prompt-injection';

type SendInput = (data: string) => Promise<unknown>;

type InjectPromptArgs = {
  providerId: string | undefined;
  text: string;
  forceBracketedPaste?: boolean;
  sendInput: SendInput;
};

export async function pastePromptInjection(args: InjectPromptArgs): Promise<void> {
  const payload = buildPromptInjectionPayload({
    providerId: args.providerId,
    text: args.text,
    forceBracketedPaste: args.forceBracketedPaste,
  });
  if (!payload) return;
  await args.sendInput(payload);
}

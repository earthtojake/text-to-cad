export function appendInitialConversationText(currentPrompt: string, text: string): string {
  const nextText = text.trim();
  if (!nextText) return currentPrompt;
  return currentPrompt ? `${currentPrompt}\n${nextText}` : nextText;
}

export function buildFinalPrompt(
  issueContext: string | null,
  userPrompt: string
): string | undefined {
  const parts: string[] = [];
  if (issueContext?.trim()) {
    parts.push(issueContext.trim());
  }
  if (userPrompt.trim()) {
    parts.push(userPrompt.trim());
  }
  return parts.length > 0 ? parts.join('\n\n') : undefined;
}

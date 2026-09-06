import {
  publishWorkbenchChatInput,
  type WorkbenchChatTarget,
} from '@core/features/conversations/api/browser/chat/workbench-chat-input-bridge';

export type CadScreenshotCaptureResult =
  | { success: true; dataUrl: string }
  | { success: false; error?: string };

export type CadScreenshotRelayResult = { success: true } | { success: false; error: string };

export async function captureCadScreenshotForWorkbenchChat({
  target,
  capture,
  name = `cad-annotation-${Date.now()}.png`,
  publish = publishWorkbenchChatInput,
}: {
  target: WorkbenchChatTarget;
  capture: () => Promise<CadScreenshotCaptureResult>;
  name?: string;
  publish?: typeof publishWorkbenchChatInput;
}): Promise<CadScreenshotRelayResult> {
  const result = await capture();
  if (!result.success) {
    return { success: false, error: result.error ?? 'Could not capture the model.' };
  }
  const delivered = await publish(target, {
    kind: 'image',
    dataUrl: result.dataUrl,
    mimeType: 'image/png',
    name,
  });
  return delivered
    ? { success: true }
    : {
        success: false,
        error: 'Wait for the chat composer to finish loading, then try again.',
      };
}
